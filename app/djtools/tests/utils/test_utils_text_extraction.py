"""Extração de texto de documentos (``djtools.utils.text_extraction``).

O PDF é montado em memória e lido pelo ``pypdf`` de verdade: nada é simulado.
"""

from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile

from djtools.utils.text_extraction import extrair_texto_documento


def _pdf_com_texto(texto_pdf: bytes) -> SimpleUploadedFile:
    """PDF de uma página cujo conteúdo escreve ``texto_pdf`` (sintaxe de string literal do PDF) em Helvetica."""
    conteudo = b'BT /F1 12 Tf 10 100 Td (' + texto_pdf + b') Tj ET'
    objetos = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        b'<< /Length %d >>\nstream\n%s\nendstream' % (len(conteudo), conteudo),
    ]
    pdf = bytearray(b'%PDF-1.4\n')
    deslocamentos = []
    for numero, objeto in enumerate(objetos, start=1):
        deslocamentos.append(len(pdf))
        pdf += b'%d 0 obj\n%s\nendobj\n' % (numero, objeto)
    inicio_xref = len(pdf)
    pdf += b'xref\n0 %d\n0000000000 65535 f \n' % (len(objetos) + 1)
    pdf += b''.join(b'%010d 00000 n \n' % deslocamento for deslocamento in deslocamentos)
    pdf += b'trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n' % (len(objetos) + 1, inicio_xref)
    return SimpleUploadedFile('trabalho.pdf', bytes(pdf), content_type='application/pdf')


def test_texto_extraido_de_pdf_com_byte_nulo_vem_sem_o_nulo() -> None:
    # PostgreSQL recusa NUL (0x00) em campo text (Sentry SUAP-WR7).
    arquivo = _pdf_com_texto(b'Resumo\\000do trabalho')

    assert extrair_texto_documento(arquivo, normalizar=False) == 'Resumodo trabalho'


def test_texto_normalizado_de_pdf_com_byte_nulo_vem_sem_o_nulo() -> None:
    arquivo = _pdf_com_texto(b'Resumo \\000 do   trabalho')

    assert extrair_texto_documento(arquivo) == 'Resumo do trabalho'
