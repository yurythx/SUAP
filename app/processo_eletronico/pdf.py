import os

from django.conf import settings
from django.http import HttpResponse
from reportlab.graphics.barcode.common import I2of5
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas
from suap import nomenclatura


def imprimir_capa_processo(processo):
    LARGURA = 210 * mm
    ALTURA = 297 * mm

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename=capa_processo.pdf'

    c = canvas.Canvas(response, pagesize=(LARGURA, ALTURA))

    imagem_logo = os.path.join(settings.STATIC_ROOT, 'comum/img/logo_instituicao.jpg')
    c.drawInlineImage(imagem_logo, 30 * mm, ALTURA - 50 * mm, 200, 52)

    c.setLineWidth(0.2 * mm)

    # Nº DO PROTOCOLO E CÓDIGO DE BARRAS
    c.rect(LARGURA - 112 * mm, ALTURA - 78 * mm, 92 * mm, 22 * mm)
    c.setFont('Helvetica-Bold', 12)
    c.drawString(LARGURA - 107 * mm, ALTURA - 62 * mm, f'Protocolo nº {processo.numero_protocolo}')

    codbarra = I2of5(processo.numero_protocolo, width=100 * mm, barHeight=10 * mm, barWidth=0.5 * mm, bearers=0, checksum=0)
    codbarra.drawOn(c, LARGURA - 114 * mm, ALTURA - 75 * mm)
    primeiro_tramite = processo.tramites.first()
    if primeiro_tramite:
        destino = str(primeiro_tramite.destinatario_setor or primeiro_tramite.destinatario_vinculo)
    else:
        destino = ''
    # INFORMAÇÕES SOBRE O DOCUMENTO
    c.rect(30 * mm, ALTURA - 129 * mm, 160 * mm, 47 * mm)
    c.setFont('Helvetica', 10)
    c.drawString(32 * mm, ALTURA - 87 * mm, 'Data: {}'.format(processo.data_hora_criacao.strftime('%d/%m/%Y')))
    c.drawString(110 * mm, ALTURA - 87 * mm, f'{nomenclatura.campus}: {processo.setor_criacao.sigla}')
    c.drawString(32 * mm, ALTURA - 93 * mm, f'Interessados: {processo.get_interessados()}')
    c.drawString(32 * mm, ALTURA - 99 * mm, 'Origem: %s' % (processo.setor_criacao and processo.setor_criacao.sigla or '-'))
    c.drawString(32 * mm, ALTURA - 105 * mm, f'Destino: {destino}')
    L = simpleSplit(f'Assunto: {processo.assunto}', 'Helvetica', 12, 150 * mm)
    y = ALTURA - 111 * mm
    for t in L:
        c.drawString(32 * mm, y, t)
        y -= 5 * mm

    # TRAMITAÇÃO
    c.setFont('Helvetica-Bold', 16)
    c.drawCentredString(110 * mm, 158 * mm, 'TRAMITAÇÃO')

    # Linhas verticais
    for h in range(30, 201, 80):
        c.line(h * mm, 20 * mm, h * mm, 152 * mm)

    # Linhas horizontais
    for v in range(20, 153, 12):
        c.line(30 * mm, v * mm, 190 * mm, v * mm)

    # Escrevendo "Data e Destino"
    i = 0
    c.setFont('Helvetica', 10)
    tramites = processo.tramites.order_by('data_hora_encaminhamento').all()
    if tramites.exists():
        for h in range(30, 130, 80):  # horizontal
            for v in range(140, 8, -12):  # vertical
                if i < tramites.count():
                    tramite = tramites[i]
                    data = tramite.data_hora_encaminhamento.strftime('%d/%m/%Y %H:%M:%S')
                    destino = str(tramite.destinatario_setor or tramite.destinatario_vinculo.pessoa.nome_usual)
                    c.drawString(h * mm + 2 * mm, v * mm + 7 * mm, f'Data: {data}')
                    c.drawString(h * mm + 2 * mm, v * mm + 3 * mm, f'Destino: {destino}')

                i += 1

    c.showPage()
    c.save()
    return response
