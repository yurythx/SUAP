import base64
import os
import tempfile

from django.conf import settings

from djtools.utils import get_datetime_now, render_pdf_from_template_with_wkhtmltopdf

SELO_IMAGEM = os.path.join(settings.BASE_DIR, 'comum', 'static', 'comum', 'img', 'selo-protocolo.png')


def documento_to_pdf(documento):
    from documento_eletronico.views import gerar_codigo_verificador_documento

    template = 'imprimir_documento_pdf.html'

    codigo_verificador = gerar_codigo_verificador_documento(documento)

    selo_data = base64.b64encode(open(SELO_IMAGEM, 'rb').read())
    selo_data = b'data:image/png;base64,' + selo_data

    qrcode_data = documento.qrcode_base64image
    agora = get_datetime_now()
    orientacao = 'portrait'

    conteudo_pdf = render_pdf_from_template_with_wkhtmltopdf(
        template,
        header_template=None,
        footer_template=None,
        context={
            'agora': agora,
            'selo_data': selo_data,
            'documento': documento,
            'qrcode_data': qrcode_data,
            'codigo_verificador': codigo_verificador,
        },
        cmd_options={
            'header-spacing': 3,
            'footer-spacing': 3,
            'orientation': orientacao,
            'enable-local-file-access': '',
            'page-height': '297mm',
            'page-width': '210mm',
            'header-left': '[title]',
            'header-font-size': 10,
        },
    )

    arquivo_temp = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
    nome_arquivo = arquivo_temp.name
    with arquivo_temp as arquivo_saida:
        arquivo_saida.write(conteudo_pdf)

    return nome_arquivo
