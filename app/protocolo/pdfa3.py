from django.http import HttpResponse
from reportlab.graphics.barcode.common import I2of5
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from comum.utils import get_logo_instituicao_file_path


def imprimir_capa_a3(processo):
    LARGURA = 420 * mm
    ALTURA = 297 * mm

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'inline; filename=capa_processo.pdf'

    c = canvas.Canvas(response, pagesize=(LARGURA, ALTURA))

    imagem_logo = get_logo_instituicao_file_path()
    if imagem_logo:
        c.drawInlineImage(imagem_logo, 220 * mm, ALTURA - 50 * mm)

    c.setLineWidth(0.2 * mm)

    # Nº DO PROTOCOLO E CÓDIGO DE BARRAS
    c.rect(LARGURA - 100 * mm, ALTURA - 78 * mm, 80 * mm, 22 * mm)
    c.setFont('Helvetica-Bold', 12)
    c.drawString(LARGURA - 96 * mm, ALTURA - 62 * mm, f'Protocolo nº {processo.numero_processo}')
    codbarra = I2of5(value=processo.numero_processo, barHeight=10 * mm, barWidth=0.5 * mm, bearers=0, checksum=0)
    codbarra.drawOn(c, LARGURA - 101 * mm, ALTURA - 75 * mm)

    # INFORMAÇÕES SOBRE O DOCUMENTO
    c.rect(220 * mm, ALTURA - 119 * mm, 180 * mm, 37 * mm)
    c.setFont('Helvetica', 12)
    c.drawString(222 * mm, ALTURA - 88 * mm, 'Data: {}'.format(processo.data_cadastro.strftime('%d/%m/%Y')))
    c.drawString(323 * mm, ALTURA - 88 * mm, f'Campus: {processo.uo.setor.sigla}')
    c.drawString(222 * mm, ALTURA - 95 * mm, f'Interessado: {processo.interessado_nome}')
    c.drawString(222 * mm, ALTURA - 109 * mm, f'Tipo: {processo.get_tipo_display()}')
    c.drawString(323 * mm, ALTURA - 102 * mm, 'Origem: {}'.format(processo.setor_origem and processo.setor_origem.sigla or '-'))
    c.drawString(323 * mm, ALTURA - 109 * mm, f'Destino: {processo.tramite_set.all()[0].orgao_recebimento!s}')
    c.drawString(222 * mm, ALTURA - 116 * mm, f'Assunto: {processo.assunto}')

    # TRAMITAÇÃO

    c.setFont('Helvetica-Bold', 16)
    c.drawCentredString(310 * mm, 158 * mm, 'TRAMITAÇÃO')

    # Linhas verticais
    for h in range(220, 401, 90):
        c.line(h * mm, 20 * mm, h * mm, 152 * mm)

    # Linhas horizontais
    for v in range(20, 153, 12):
        c.line(220 * mm, v * mm, 400 * mm, v * mm)

    # Escrevendo "Data e Destino"
    c.setFont('Helvetica', 11)
    for h in range(220, 320, 90):  # horizontal
        for v in range(20, 150, 12):  # vertical
            c.drawString(h * mm + 2 * mm, v * mm + 4 * mm, 'Data: ___/___/______    Destino:')

    c.showPage()
    c.save()
    return response
