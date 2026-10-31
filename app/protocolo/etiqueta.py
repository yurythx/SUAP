from django.http import HttpResponse
from reportlab.graphics.barcode.common import I2of5
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

from protocolo.models import Tramite


def abreviar_nome(nome):
    excecoes = ['DE', 'DA', 'DAS', 'DOS', 'DO', 'DI']
    fullname = nome.split(' ')
    nome = fullname[0]
    unome = fullname[-1]
    del fullname[0]
    del fullname[fullname.index(fullname[-1])]

    for n in fullname:
        isexcecao = False
        for e in excecoes:
            if n.upper() == e:
                isexcecao = True
                nome = f'{nome} {n}'
                break
        if isexcecao:
            continue
        nome = f'{nome} {n[0]}'

    nome = f'{nome} {unome}'

    return nome


def get_primeiro_tramite(processo):
    caminho = ''
    if Tramite.objects.filter(processo=processo).order_by('ordem').exists():
        tramites_processo = Tramite.objects.filter(processo=processo).order_by('ordem')[0]
        if tramites_processo.is_interno():
            setor_atual = tramites_processo.orgao_interno_recebimento
            while setor_atual is not None:
                caminho = f' - {setor_atual!s}{caminho}'
                setor_atual = setor_atual.superior
            lista = list(caminho)
            lista[0:3] = []
            caminho = ''.join(lista)
        else:
            caminho = str(processo.tramite_set.all()[0].orgao_recebimento)

    return caminho


def imprimir_etiqueta(processo):
    LARGURA = 88 * mm
    ALTURA = 35 * mm
    FONTSIZE = 8
    ESPACO = 3
    inicio = 14
    inicioh = 5
    inicioh2 = 28

    response = HttpResponse(content_type='application/pdf')

    c = canvas.Canvas(response, pagesize=(LARGURA, ALTURA))
    c.setTitle(f'Etiqueta do Processo nº {processo.numero_processo}')
    c.setFont('Times-Bold', FONTSIZE)
    c.drawString(35 * mm, ALTURA - 5.7 * mm, 'PROC. Nº:')
    c.setFont('Times-Bold', FONTSIZE + 2)
    c.drawString(49.5 * mm, ALTURA - 5.7 * mm, f'{processo.numero_processo}')
    c.setFont('Times-Bold', FONTSIZE)
    c.drawString(35 * mm, ALTURA - 8.5 * mm, 'DATA:')
    c.setFont('Times-Roman', FONTSIZE)
    c.drawString(49.5 * mm, ALTURA - 8.5 * mm, processo.data_cadastro.strftime('%d/%m/%Y'))
    c.setFont('Times-Bold', FONTSIZE)
    c.drawString(35 * mm, ALTURA - 11 * mm, 'OPER.:')
    c.setFont('Times-Roman', FONTSIZE - 1.7)
    c.drawString(49.5 * mm, ALTURA - 11 * mm, f'{abreviar_nome(processo.vinculo_cadastro.pessoa.nome.upper())}')

    codbarra = I2of5(processo.numero_processo, barHeight=8 * mm, barWidth=0.2 * mm, bearers=0, checksum=0)
    codbarra.drawOn(c, 3.5 * mm, ALTURA - 11 * mm)

    inicio += 1
    c.setFont('Times-Bold', FONTSIZE)
    c.drawString(inicioh * mm, ALTURA - (inicio) * mm, 'INTERESSADO:')
    L = simpleSplit(f'{processo.interessado_nome.upper()}', 'Times-Roman', FONTSIZE - 1, (((LARGURA - 20) / mm) - inicioh - inicioh2) * mm)
    y = ALTURA - (inicio) * mm
    for t in L:
        c.drawString(inicioh2 * mm, y, t)
        inicio += 2.5
        y -= 2.5 * mm
    inicio += ESPACO - 2.5
    c.setFont('Times-Bold', FONTSIZE)
    c.drawString(inicioh * mm, ALTURA - (inicio) * mm, 'ASSUNTO:')
    c.setFont('Times-Roman', FONTSIZE)
    L = simpleSplit(f'{processo.assunto}', 'Times-Roman', FONTSIZE, ((LARGURA / mm) - inicioh - inicioh2 - 3) * mm)
    y = ALTURA - (inicio) * mm
    for t in L:
        c.drawString(inicioh2 * mm, y, t)
        inicio += 2.9
        y -= 2.9 * mm
    inicio += ESPACO - 2.9

    inicio += 1
    c.setFont('Times-Bold', FONTSIZE + 2)
    c.drawString(inicioh * mm, ALTURA - (inicio) * mm, f'{get_primeiro_tramite(processo)}')

    c.showPage()
    c.save()
    return response
