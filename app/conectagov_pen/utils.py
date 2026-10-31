import hashlib
import io
from datetime import datetime

from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import PKCS1_v1_5
from django.conf import settings

from comum.models import Configuracao
from conectagov_pen.models import MapeamentoTiposDocumento
from djtools.utils import b64encode

PRIVATE_ROOT_DIR = 'private-media/conectagov_pen'


def monta_recibo(idt: int | str, nre: int | str, hashsDosComponentes: list[str]) -> dict:
    """<recibo><IDT>5235</IDT><NRE>0000004385642018</NRE><dataDeRecebimento>2018-07-31T18:42:59.000Z</dataDeRecebimento>
    <hashDoComponenteDigital>CUNN8SQz6cQHMSkEr2U+DprySgUUzqXtDN3tWXI72ec=</hashDoComponenteDigital></recibo>"""
    # Formatos de data permitidos:  "yyyy-MM-dd\'T\'HH:mm:ss.SSSZ", "yyyy-MM-dd\'T\'HH:mm:ss.SSS\'Z\'", "EEE, dd MMM yyyy HH:mm:ss zzz", "yyyy-MM-dd"
    # data_utc = timezone.make_aware(datetime.datetime.now()).strftime("%Y-%m-%dT%H:%M:%S%Z:00")
    (dt, micro) = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f').split('.')
    data_utc = f'{dt}.{int(int(micro) / 1000):03d}Z'
    # Formato que estava sendo usado mas parou de funcionar
    # data_utc = timezone.make_aware(datetime.now()).strftime("%Y-%m-%dT%H:%M:%S.000%Z:00")
    recibo_xml = '<recibo><IDT>' + str(idt) + '</IDT><NRE>' + str(nre) + '</NRE>'
    recibo_xml += '<dataDeRecebimento>' + data_utc + '</dataDeRecebimento>'

    # Ordena lista com hahs dos componentes
    if hashsDosComponentes and len(hashsDosComponentes) > 1:
        hashsDosComponentes.sort()
        for hash in hashsDosComponentes:
            recibo_xml += '<hashDoComponenteDigital>' + hash + '</hashDoComponenteDigital>'
    else:
        recibo_xml += '<hashDoComponenteDigital>' + hashsDosComponentes[0] + '</hashDoComponenteDigital>'
    recibo_xml += '</recibo>'

    recibo_json = {'dataDeRecebimento': data_utc, 'hashDaAssinatura': assina_recibo(recibo_xml).decode()}

    return recibo_json


def assina_recibo(data):
    """Assina recibo de conclusao do tramite"""
    digest = SHA256.new()
    digest.update(data.encode('utf-8'))

    with open(Configuracao.get_valor_por_chave(app='conectagov_pen', chave='pathCertificadoPrivado_pen')) as myfile:
        private_key = RSA.importKey(myfile.read())

    # Load private key and sign message
    signer = PKCS1_v1_5.new(private_key)
    sig = signer.sign(digest)

    # Load public key and verify message
    verifier = PKCS1_v1_5.new(private_key.publickey())
    verified = verifier.verify(digest, sig)
    # era usado assert para verificar a assinatura
    # assert verified, 'Signature verification failed'
    hash_sign = b64encode(sig)
    if verified:
        return hash_sign
    else:
        return None


def get_hash_documento(file_content):
    """Retorna um hash (sha256) do conteudo do arquivo"""
    return b64encode(hashlib.sha256(file_content).digest())


def dict_to_choices(dict_, key_value, key_label):
    choices = ()
    if dict_:
        for d in dict_:
            choice = ((d[key_value], d[key_label]),)
            choices += choice
    return choices


def dict_to_choices_estruturas(dict_):
    choices = ()
    if dict_:
        for d in dict_:
            if d['hierarquia'][2]['sigla']:
                choice = (
                    (
                        d['numeroDeIdentificacaoDaEstrutura'],
                        d['nome'] + ' - ' + d['hierarquia'][0]['sigla'] + ' / ' + d['hierarquia'][1]['sigla'] + ' / ' + d['hierarquia'][2]['sigla'],
                    ),
                )
            elif d['hierarquia'][1]['sigla']:
                choice = (
                    (d['numeroDeIdentificacaoDaEstrutura'], d['nome'] + ' - ' + d['hierarquia'][0]['sigla'] + ' / ' + d['hierarquia'][1]['sigla']),
                )
            elif d['hierarquia'][0]['sigla']:
                choice = ((d['numeroDeIdentificacaoDaEstrutura'], d['nome'] + ' - ' + d['hierarquia'][0]['sigla']),)
            else:
                choice = ((d['numeroDeIdentificacaoDaEstrutura'], d['nome']),)
            choices += choice
    return choices


def monta_retorno_autocomplete(dict_):
    total = 0
    items = []
    if dict_:
        for d in dict_:
            ident = d.get('numeroDeIdentificacaoDaEstrutura')
            if ident:
                choice = d.get('nome', '-') + ' - ' + d.get('sigla', '-')
                for estrutura in d.get('hierarquia', []):
                    choice += ' / ' + estrutura.get('sigla', '-')
                total += 1
                item = {'text': choice, 'html': '<span>' + choice + '</span>', 'id': d['numeroDeIdentificacaoDaEstrutura']}
                items.append(item)
    return {'items': items, 'total': total}


def tamanho_em_bytes(file_content):
    size = len(file_content)
    return size


def tamanho_em_mb(file_content):
    size = len(file_content) / 1024
    return size


def get_nivel_acesso_documento(nivel_acesso):
    """Função que altera o nível de acesso dos documentos do suap para o padrão do barramento
    que é 1 - publico, 2 - restrito e 3 - sigiloso"""
    if nivel_acesso == 3:
        return 1
    elif nivel_acesso == 1:
        return 3
    else:
        return 2


def as_pdf(html):
    from weasyprint import HTML

    try:
        pdf_bytes = io.BytesIO()
        HTML(string=html, base_url=settings.SITE_URL).write_pdf(pdf_bytes)
        pdf_bytes.seek(0)
    except Exception:
        pdf_bytes = io.BytesIO()
        HTML(string=html.decode('utf-8', 'ignore'), base_url=settings.SITE_URL).write_pdf(pdf_bytes)
        pdf_bytes.seek(0)
    return pdf_bytes


def processo_possui_tipos_de_documentos_nao_mapeados_no_envio(documentos):
    """
    :param documentos:
    :return:
    """
    for documento in documentos:
        qtd_documentos_nao_mapeados = 0
        if documento.classe in ['documento_texto', 'documento_digitalizado']:
            if not MapeamentoTiposDocumento.objects.filter(tipo_doc_suap=documento.documento.tipo).exists():
                qtd_documentos_nao_mapeados += 1
        elif documento.classe == 'despacho':
            if not MapeamentoTiposDocumento.objects.filter(tipo_doc_barramento_pen=42).exists():
                qtd_documentos_nao_mapeados += 1
        elif documento.classe == 'minuta':
            if not MapeamentoTiposDocumento.objects.filter(tipo_doc_barramento_pen=83).exists():
                qtd_documentos_nao_mapeados += 1

        if qtd_documentos_nao_mapeados:
            return True

    return False


def processo_possui_tipos_de_documentos_nao_mapeados_no_recebimento(metadados_documentos):
    for metadados_documento in metadados_documentos:
        if not MapeamentoTiposDocumento.objects.filter(tipo_doc_barramento_pen=int(metadados_documento['especie']['codigo'])).exists():
            return True
    return False


def get_tipos_de_documentos_nao_mapeados_no_recebimento(metadados_documentos):
    tipos_nao_mapeados = []
    for metadados_documento in metadados_documentos:
        if not MapeamentoTiposDocumento.objects.filter(tipo_doc_barramento_pen=int(metadados_documento['especie']['codigo'])).exists():
            tipos_nao_mapeados.append('{}-{}'.format(metadados_documento['especie']['codigo'], metadados_documento['especie']['nomeNoProdutor']))
    return tipos_nao_mapeados


def strdecode(content):
    if isinstance(content, str):
        return content
    elif isinstance(content, bytes):
        return content.decode()
