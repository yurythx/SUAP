"""
Assinatura digital de PDFs com serviço externo ICP-Edu.

Dependências:
    pip install pypdf Pillow

Sobre endesive e o placeholder PKCS#7:
    endesive.pdf.cms.sign() lida com o placeholder internamente, mas exige
    que a chave privada esteja LOCAL. Como aqui a assinatura é feita por um
    serviço externo (service.sign_hash), o fluxo de "preparar → hash → assinar
    → injetar" precisa continuar manual — é exatamente isso que endesive faz
    internamente, mas sem expor esse fluxo publicamente para chaves externas.

    O ganho real de endesive seria se o serviço externo retornasse um blob
    PKCS#7 completo (DER), permitindo:
        signed_pdf = endesive.pdf.cms.sign(datau, dct, signed_value=pkcs7_der)
    Se o serviço evoluir para isso, a troca vale a pena.

    Por ora, a melhoria mais impactante foi substituir todo o parsing manual
    (xref, trailer, root, size, páginas) pelo pypdf, eliminando a fragilidade
    com PDFs que usam cross-reference streams (PDF 1.5+).
"""

import base64
import hashlib
import os
import re
import tempfile
from datetime import datetime, timedelta
from io import BytesIO

from django.conf import settings
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader

from comum.models import APIExterna

SIGNATURE_SIZE = 18944
BYTERANGE_PLACEHOLDER = '[                                  ]'


class PdfSigner:
    """
    Assina digitalmente arquivos PDF usando o serviço ICP-Edu.

    Fluxo principal:
      1. Instanciar com o caminho do PDF e o assinante.
      2. Chamar sign(coords, page_no) para gerar o PDF assinado.
    """

    def __init__(self, path: str, signer, signer_email: str = ''):
        self.api_externa = APIExterna.ICPEDU
        self.service = self.api_externa.get_service()
        self.service.set_signer(signer, email=signer_email)

        with open(path, 'rb') as fp:
            self.content: bytes = fp.read()

        self.path = path.split('.', maxsplit=1)[0]
        self.offset = len(self.content)
        self.byterange: list[int] = []
        self.data: list[str] = []
        self.xref: list[str] | None = None

        # pypdf cuida do parsing: cross-reference streams, linearização, etc.
        self._reader = PdfReader(BytesIO(self.content))
        self._parse_structure()

    # -------------------------------------------------------------------------
    # Parsing — delegado ao pypdf
    # -------------------------------------------------------------------------

    def _parse_structure(self):
        """
        Extrai root, size, startxref e mapa de offsets dos objetos.

        pypdf lida transparentemente com:
          - Tabelas xref clássicas
          - Cross-reference streams (PDF 1.5+)
          - PDFs linearizados
          - Múltiplas revisões incrementais
        """
        trailer = self._reader.trailer

        # Referência do /Root: "num generation" (ex: "1 0")
        # pypdf pode retornar um IndirectObject ou o objeto já resolvido,
        # dependendo da versão e do PDF. Tratamos os dois casos.
        root_ref = trailer.raw_get('/Root')
        if hasattr(root_ref, 'idnum'):
            # IndirectObject — acesso direto aos atributos
            self.root = f'{root_ref.idnum} {root_ref.generation}'
        else:
            # Objeto já resolvido — busca a referência pelo indirect_reference
            resolved = trailer['/Root']
            ref = getattr(resolved, 'indirect_reference', None)
            if ref:
                self.root = f'{ref.idnum} {ref.generation}'
            else:
                # Fallback: regex no conteúdo bruto
                match = re.search(rb'/Root (\d+) (\d+) R', self.content)
                if not match:
                    raise ValueError('Referência /Root não encontrada no PDF.')
                self.root = f'{match.group(1).decode()} {match.group(2).decode()}'

        self.size = int(trailer['/Size'])

        # Localização do último startxref (necessária para o novo trailer)
        self.startxref = [self._find_last_startxref()]

        # Mapa de offsets para leitura incremental de objetos brutos
        self.objects = self._build_objects_map()

    def _find_last_startxref(self) -> int:
        """Extrai o último offset startxref via regex."""
        matches = re.findall(rb'startxref[\n\r ]*(\d+)', self.content)
        if not matches:
            raise ValueError('Nenhum startxref encontrado no PDF.')
        return int(matches[-1])

    def _build_objects_map(self) -> dict[str, int]:
        """
        Constrói o mapa "num gen" → offset em bytes para leitura incremental.

        Estratégia em duas etapas:
          1. pypdf (via xref interno) — rápido e cobre a maioria dos casos.
          2. Scan por regex no conteúdo bruto — garante que objetos não
             listados na xref do pypdf (ex: PDFs com xref streams parciais
             ou revisões incrementais) sejam incluídos.

        O scan por regex tem precedência, pois o offset no arquivo raw
        é sempre a fonte da verdade.
        """
        objects: dict[str, int] = {}

        # 1. pypdf
        try:
            for generation, entries in self._reader.xref.items():
                for obj_num, offset in entries.items():
                    if offset:
                        objects[f'{obj_num} {generation}'] = offset
        except Exception:
            pass  # prossegue para o scan

        # 2. Scan no conteúdo bruto: localiza "num gen obj" diretamente
        for match in re.finditer(rb'(\d+) (\d+) obj', self.content):
            obj_num = match.group(1).decode()
            generation = match.group(2).decode()
            offset = match.start()
            objects[f'{obj_num} {generation}'] = offset  # raw sobrescreve

        return objects

    # -------------------------------------------------------------------------
    # Navegação de páginas — pypdf torna isso trivial
    # -------------------------------------------------------------------------

    def _get_page_key(self, page_no: int) -> str:
        """Retorna 'num gen' do objeto da página (base 1)."""
        page = self._reader.pages[page_no - 1]
        ref = page.indirect_reference
        return f'{ref.idnum} {ref.generation}'

    def _get_page_dimensions(self, page_no: int) -> tuple[float, float]:
        """Retorna (largura, altura) da página em pontos PDF."""
        page = self._reader.pages[page_no - 1]
        return float(page.mediabox.width), float(page.mediabox.height)

    # -------------------------------------------------------------------------
    # Leitura de objetos brutos (necessário para escrita incremental)
    # -------------------------------------------------------------------------

    def _obj(self, key: str | None = None) -> bytes:
        """
        Retorna o conteúdo de um objeto PDF pelo identificador 'num gen'.

        Estratégia:
          1. Leitura direta no arquivo (offset conhecido) — objetos clássicos.
          2. Fallback via pypdf — objetos compactados em ObjStm (PDF 1.5+),
             que não existem como 'N 0 obj' literal no arquivo.
        """
        from io import BytesIO

        from pypdf.generic import IndirectObject

        key = key or self.root

        # 1. Objeto acessível diretamente no arquivo
        if key in self.objects:
            start = self.objects[key]
            end = self.content[start:].index(b'endobj') + 6
            return self.content[start : start + end].replace(b'\r', b'') + b'\n'

        # 2. Objeto compactado em ObjStm — pypdf descomprime e serializa
        num, gen = (int(x) for x in key.split())
        pdf_obj = self._reader.get_object(IndirectObject(num, gen, self._reader))
        buf = BytesIO()
        pdf_obj.write_to_stream(buf)
        return f'{key} obj\n'.encode() + buf.getvalue() + b'\nendobj\n'

    def _next_obj_num(self, increment: int = 1) -> int:
        """Próximo número de objeto disponível para adição incremental."""
        return max(int(k.split()[0]) for k in self.objects) + increment

    # -------------------------------------------------------------------------
    # Montagem incremental do PDF
    # -------------------------------------------------------------------------

    def _add_object(self, data: str):
        """Adiciona um objeto ao incremento e registra na xref."""
        offset_str = str(self.offset).rjust(10, '0')
        self.offset += len(data)
        self.data.append(data)

        if self.xref is None:
            self.xref = ['xref', '0 1', '0000000000 65535 f\r']

        self.xref.append(f'{data.split(maxsplit=1)[0]} 1')
        self.xref.append(f'{offset_str} 00000 n\r')

    def _finalize(self):
        """Escreve a xref table e o trailer final do incremento."""
        xref_start = str(self.offset)
        num_objects = self.size + len(self.xref) - 5
        trailer_body = f'\ntrailer\n<<\n/Size {num_objects}\n/Root {self.root} R\n/Prev {self.startxref[-1]}\n>>\n'
        trailer_block = '\n'.join(self.xref) + trailer_body + f'startxref\n{xref_start}\n%%EOF'
        self.offset += len(trailer_block)
        self.data.append(trailer_block)

    def _total_length(self) -> int:
        return len(self.content) + sum(len(d) for d in self.data)

    # -------------------------------------------------------------------------
    # Carimbo visual
    # -------------------------------------------------------------------------

    def stamp(self, name: str) -> str:
        """Gera um JPEG com o carimbo de assinatura e retorna o caminho."""
        width, height = 900, 200
        date_str = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        base_url = self.api_externa.url_base
        font_dir = os.path.join(settings.BASE_DIR, 'comum', 'static/comum/font')

        font = ImageFont.truetype(os.path.join(font_dir, 'MicrosoftSansSerif.ttf'), 25)
        bold = ImageFont.truetype(os.path.join(font_dir, 'MicrosoftSansSerifBold.ttf'), 25)

        img = Image.new('RGB', (width, height), (255, 255, 255))
        draw = ImageDraw.Draw(img)

        text_x, text_y = 380, 10
        for text, f in [
            ('DOCUMENTO ASSINADO DIGITALMENTE', font),
            (name, bold),
            (f'Data/Hora: {date_str}', font),
            (f'{base_url}/verifica', font),
        ]:
            draw.text((text_x, text_y), text, (0, 0, 0), font=f)
            text_y += 35

        logo_path = os.path.join(os.path.dirname(__file__), 'static', 'comum', 'img', 'icpedu.png')
        logo = Image.open(logo_path)
        img.paste(logo.resize((int(logo.width * 0.6), int(logo.height * 0.6))), (5, 10))

        tmp = tempfile.NamedTemporaryFile(suffix='.jpeg', delete=False)
        img.convert('RGB').save(tmp.name, format='jpeg')
        return tmp.name

    def _compute_stamp_rect(self, coords: str, page_no: int) -> tuple[float, float, int, int]:
        """Converte 'top%:left%' para (x, y, largura, altura) em pontos PDF."""
        page_w, page_h = self._get_page_dimensions(page_no)
        stamp_w, stamp_h = 170, 50
        top_pct, left_pct = (float(v) for v in coords.split(':'))

        pos_x = (left_pct * page_w) / 100
        pos_y = ((100 - top_pct) * page_h) / 100 - stamp_h
        return pos_x, pos_y, stamp_w, stamp_h

    # -------------------------------------------------------------------------
    # Placeholder PKCS#7 e cálculo do hash
    # -------------------------------------------------------------------------

    def hash(self, coords: str = '0:0', page_no: int = 1) -> str:
        """
        Monta a estrutura incremental do PDF com o placeholder /Contents zerado
        e retorna o SHA-256 do intervalo coberto pelo /ByteRange.

        Este é o valor que deve ser enviado ao serviço externo de assinatura.
        """
        page_key = self._get_page_key(page_no)
        stamp_x, stamp_y, stamp_w, stamp_h = self._compute_stamp_rect(coords, page_no)
        signer_name = self.service.signer.nome
        stamp_path = self.stamp(signer_name)

        n = self._next_obj_num
        date_str = (datetime.now() + timedelta(hours=6)).strftime("D:%Y%m%d%H%M%S+00'00'")
        rect = f'[{stamp_x} {stamp_y} {stamp_x + stamp_w} {stamp_y + stamp_h}]'

        # /Root atualizado com AcroForm
        updated_root = (
            self._obj()
            .decode()
            .replace(
                '>>',
                f'/AcroForm <<\n/Fields [{n(1)} 0 R]\n/SigFlags 3\n>>\n>>',
            )
        )
        self._add_object(updated_root)

        # /Page atualizado com referência à anotação de assinatura
        page_content = self._obj(page_key).decode()
        if '/Annots' in page_content:
            page_content = page_content.replace('/Annots [', f'/Annots [{n(1)} 0 R ')
        else:
            page_content = page_content.replace('/Page', f'/Page /Annots [{n(1)} 0 R]')
        self._add_object(page_content)

        # Widget visível do campo de assinatura
        widget = (
            f'{n(1)} 0 obj\n<<\n/FT /Sig\n/Type /Annot\n/Subtype /Widget\n/F 132\n'
            f'/T (Signature{n(1)})\n/V {n(2)} 0 R\n/P {page_key} R\n'
            f'/Rect {rect}\n/AP {n(3)} 0 R\n>>\nendobj\n'
        )

        # Objeto /Sig — /Contents zerado é o placeholder PKCS#7
        sig_obj = (
            f'{n(2)} 0 obj\n<<\n/Type /Sig\n/Filter /Adobe.PPKLite\n'
            f'/SubFilter /adbe.pkcs7.detached\n/M ({date_str})\n'
            f'/Contents <{"0" * SIGNATURE_SIZE}>\n/ByteRange {BYTERANGE_PLACEHOLDER}\n'
            f'/Name ({signer_name})\n>>\nendobj\n'
        )

        # Aparência visual: Form XObject → imagem JPEG em ASCII85
        stream = f'q\n{stamp_w} 0 0 {stamp_h} 0 0 cm\n/Img1 Do\nQ'
        ap_dict = f'{n(3)} 0 obj\n<<\n/N {n(4)} 0 R\n>>\nendobj\n'
        ap_form = (
            f'{n(4)} 0 obj\n<</Type/XObject/Subtype/Form'
            f'/Resources<</XObject<</Img1 {n(5)} 0 R>>>>'
            f'/BBox[0 0 {stamp_w} {stamp_h}]/Length {len(stream)}>>\n'
            f'stream\n{stream}\nendstream\nendobj\n'
        )
        img_data = base64.a85encode(open(stamp_path, 'rb').read()).decode()
        ap_image = (
            f'{n(5)} 0 obj\n<<\n/BitsPerComponent 8 /ColorSpace /DeviceRGB'
            f'/Filter [ /ASCII85Decode /DCTDecode ] /Length {len(img_data)}'
            f'/Subtype /Image /Type /XObject /Width 900 /Height 200'
            f'/Resources<<    >> >>\nstream\n{img_data}\nendstream\nendobj\n'
        )

        self._add_object(widget)
        sig_start = self.offset + sig_obj.index('/Contents') + 10
        sig_end = sig_start + SIGNATURE_SIZE + 2
        self._add_object(sig_obj)
        self._add_object(ap_dict)
        self._add_object(ap_form)
        self._add_object(ap_image)
        self._finalize()

        # Substitui o placeholder /ByteRange com os valores reais
        self.byterange = [0, sig_start, sig_end, self._total_length() - sig_end]
        byterange_str = '[{} {} {} {}]'.format(*self.byterange).ljust(len(BYTERANGE_PLACEHOLDER))
        self.data[3] = self.data[3].replace(BYTERANGE_PLACEHOLDER, byterange_str)

        for chunk in self.data:
            self.content += chunk.encode()

        i, j, x, y = self.byterange
        return hashlib.sha256(self.content[i : i + j] + self.content[x : x + y]).hexdigest()

    # -------------------------------------------------------------------------
    # API pública
    # -------------------------------------------------------------------------

    def signed(self, name: str) -> bool:
        """Verifica se o PDF já contém uma assinatura com o nome informado."""
        return f'/Name ({name})'.encode() in self.content

    def sign(self, coords: str = '0:0', page_no: int = 1, path: str | None = None) -> str:
        """
        Assina o PDF e salva o resultado.

        Args:
            coords:  Posição do carimbo em percentual "top:left" (ex: "10.5:20.0").
            page_no: Página onde o carimbo será inserido (base 1).
            path:    Caminho de saída. Padrão: <nome_original>-signed.pdf.

        Returns:
            Caminho do arquivo assinado.
        """
        document_hash = self.hash(coords, page_no)
        signature = self.service.sign_hash(document_hash)
        output_path = path or f'{self.path}-signed.pdf'

        with open(output_path, 'wb') as fp:
            if signature:
                i, j, x, y = self.byterange
                fp.write(self.content[i : i + j] + b'<' + signature.ljust(SIGNATURE_SIZE, '0').encode() + b'>' + self.content[x : x + y])
            else:
                fp.write(self.content)

        return output_path
