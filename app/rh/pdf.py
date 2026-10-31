import os
from datetime import date, datetime

from django.conf import settings
from django.http import HttpResponse
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas

from comum.models import Configuracao
from djtools.storages import cache_file


def dateToStr(date=None):
    """Recebe objeto Date e converte para uma String no formato dd/mm/aaaa"""
    if not date:
        date = datetime.today()
    return date.strftime('%d/%m/%Y')


def getNomeMes(mes):
    meses = {
        1: 'Janeiro',
        2: 'Fevereiro',
        3: 'Março',
        4: 'Abril',
        5: 'Maio',
        6: 'Junho',
        7: 'Julho',
        8: 'Agosto',
        9: 'Setembro',
        10: 'Outubro',
        11: 'Novembro',
        12: 'Dezembro',
    }
    return meses[mes]


def getDataExtenso(data=None):
    if not data:
        data = date.today()
    return f'{data.day} de {getNomeMes(data.month)} de {data.year}'


def imprime_cracha(servidores):
    CRACHA_DIR = os.path.join(os.getcwd(), settings.BASE_DIR, 'rh/cracha/')

    if not isinstance(servidores, list):
        servidores = [servidores]

    altura = 85 * mm
    largura = 54 * mm

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename=cracha.pdf'
    c = Canvas(response, pagesize=(largura, altura))

    for servidor in servidores:
        nome_imagem_bg = 'cracha-servidor.png'
        if servidor.eh_estagiario:
            nome_imagem_bg = 'cracha-estagiario.png'

        imagemfundo = os.path.join(os.getcwd(), CRACHA_DIR, nome_imagem_bg)
        sangue = f'{servidor.pessoa_fisica.grupo_sanguineo}{servidor.pessoa_fisica.fator_rh}'

        # foto do servidor
        imagemfoto = servidor.get_foto_path()

        # imagem para indicar o tipo sanguíneo
        # gota_path = str(sangue).lower().replace(' ', '') + '.jpg'
        # imagemgota = os.path.join(os.getcwd(), CRACHA_DIR, gota_path)

        # manipulação das imagens
        c.drawInlineImage(imagemfundo, 0.2 * mm, 0.2 * mm, largura - 0.2 * mm, altura - 0.2 * mm, preserveAspectRatio=True)

        c.setFillColorRGB(1, 1, 1)
        font_size = 10
        left = 3.7
        if sangue == 'AB+' or sangue == 'AB-':
            font_size = 7
            left = 3.4
        c.setFont('Helvetica-Bold', font_size)
        c.drawString(left * mm, 3 * mm, sangue)

        # c.drawInlineImage(imagemgota, 3*mm, 1.4*mm, 5.65*mm, 7.5*mm)
        c.drawInlineImage(imagemfoto, 13.3 * mm, 25.0 * mm, 27.4 * mm, 36.5 * mm)

        # manipulação da matrícula
        nome = servidor.pessoa_fisica.nome.upper()
        if servidor.pessoa_fisica.nome_usual:
            nome = servidor.pessoa_fisica.nome_usual.upper()
        if hasattr(servidor, 'nome_social_cracha') and servidor.pessoa_fisica.nome_social_cracha:
            nome = servidor.pessoa_fisica.nome_social_cracha.upper()
        elif hasattr(servidor, 'nome_sugerido_cracha') and servidor.pessoa_fisica.nome_sugerido_cracha:
            nome = servidor.pessoa_fisica.nome_sugerido_cracha.upper()

        c.setFillColorRGB(0, 0, 0)
        c.setFont('Helvetica-Bold', 10)
        c.drawCentredString(largura / 2, 20 * mm, nome)
        c.drawCentredString(largura / 2, 16 * mm, str(servidor.matricula))
        if servidor.eh_estagiario:
            c.setFont('Helvetica-Bold', 9)
            c.drawCentredString(largura / 2, 12 * mm, 'ESTAGIÁRIO')
        c.rotate(90)

        c.showPage()

    # salva o pdf
    c.save()

    return response


def calculaDigitoCracha(matricula):
    digito = 0
    for i in range(1, len(matricula) + 1):
        j = i + 1
        if j > 9:
            j = j - 9 + 1
        d = matricula[-i]
        digito = digito + j * int(d)
    digito = digito % 11
    if digito == 0 or digito == '':
        digito = 0
    else:
        digito = 11 - digito
    return str(digito)


def imprime_carteira_funcional(servidores, config=None):
    if not isinstance(servidores, list):
        servidores = [servidores]

    # altura = 120*mm
    # largura = 85*mm

    # Descomentar a linha seguinte para escolher local com imagens de carteira funcional
    # CARTEIRA_DIR = os.path.join(os.getcwd(), settings.BASE_DIR , "rh/carteira/")

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename=carteira.pdf'
    c = Canvas(response, pagesize=A4)

    # Descomentar a linha seguinte para escolher imagem que será usada como plano de fundo
    # imagemfundo = os.path.join(os.getcwd(), CARTEIRA_DIR, 'carteira_funcional_2016.jpg')

    salto = 78.5
    count = 1
    for servidor in servidores:
        c.setFont('Helvetica-Bold', 5.2)
        #
        # dados normais
        nome = servidor.pessoa_fisica.nome.upper()
        matricula = servidor.matricula
        tipo_sanguineo = f'{servidor.grupo_sanguineo}{servidor.pessoa_fisica.fator_rh}'
        nome_mae = servidor.pessoa_fisica.nome_mae.upper()
        rg = f'{servidor.pessoa_fisica.rg} {servidor.pessoa_fisica.rg_orgao}/{servidor.pessoa_fisica.rg_uf}'
        cpf = servidor.pessoa_fisica.cpf
        nascimento_data = servidor.pessoa_fisica.nascimento_data.strftime('%d/%m/%Y')
        cargo_emprego = servidor.cargo_emprego.nome

        #
        # naturalidade
        municipio = ''
        uf = ''
        if servidor.pessoa_fisica.nascimento_municipio:
            municipio = servidor.pessoa_fisica.nascimento_municipio.nome or ''
            uf = servidor.pessoa_fisica.nascimento_municipio.uf or ''
        naturalidade = f'{municipio}/{uf}'

        #
        # data de emissão
        data_emissao = f'{Configuracao.get_valor_por_chave("comum", "municipio_sede")}/{Configuracao.get_valor_por_chave("comum", "instituicao_estado")}, '.format(
            datetime.now().strftime('%d/%m/%Y')
        )

        sl = salto * (count - 1)

        horizontal_extra = 6
        vertical_extra = 2

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.fields['data_emissao'] = (
                f'{Configuracao.get_valor_por_chave("comum", "municipio_sede")}/{Configuracao.get_valor_por_chave("comum", "instituicao_estado")}'
            )

        #
        # ajuste técnico :D
        if count == 1:
            vertical_extra = vertical_extra + 1.2 + ((config and config.margem_top_bloco_1 or 0) * -1)
        if count == 2:
            vertical_extra = vertical_extra - 1 + ((config and config.margem_top_bloco_2 or 0) * -1)
        if count == 3:
            vertical_extra = vertical_extra - 2.4 + ((config and config.margem_top_bloco_3 or 0) * -1)
        if count == 4:
            vertical_extra = vertical_extra - 4 + ((config and config.margem_top_bloco_4 or 0) * -1)

        #
        # imagem de fundo para orientação na posição dos elementos
        # c.drawImage(imagemfundo, -5, (228 - sl) * mm, 212 * mm, 69 * mm)

        #
        # Foto do servidor

        # ponytail: servidor.foto agora é property do vínculo (pode ser None sem vínculo/foto); só desenha se houver foto.
        foto = servidor.foto
        if foto:
            remote_filename = foto.name.replace('fotos/', 'fotos/150x200/')
            imagemfoto = cache_file(remote_filename)
            c.drawImage(
                imagemfoto, (197 + horizontal_extra), ((256 + vertical_extra) - sl) * mm, 28 * mm, 34 * mm, mask='auto', preserveAspectRatio=True
            )
        #
        # matrícula
        c.drawString((32 + horizontal_extra), ((250.5 + vertical_extra) - sl) * mm, matricula)
        #
        # nome
        c.drawString((32 + horizontal_extra), ((242.5 + vertical_extra) - sl) * mm, nome)
        #
        # CPF
        c.drawString((322 + horizontal_extra), ((284 + vertical_extra) - sl) * mm, cpf)
        #
        # RG
        c.drawString((440 + horizontal_extra), ((284 + vertical_extra) - sl) * mm, rg)
        #
        # cargo
        c.drawString((322 + horizontal_extra), ((276.2 + vertical_extra) - sl) * mm, cargo_emprego)
        #
        # tipo sanguíneo
        c.drawString((460 + horizontal_extra), ((276.2 + vertical_extra) - sl) * mm, tipo_sanguineo)
        #
        # naturalidade
        c.drawString((322 + horizontal_extra), ((268.3 + vertical_extra) - sl) * mm, naturalidade)
        #
        # data nascimento
        c.drawString((460 + horizontal_extra), ((268.4 + vertical_extra) - sl) * mm, nascimento_data)
        #
        # nome da mãe
        c.drawString((322 + horizontal_extra), ((260 + vertical_extra) - sl) * mm, nome_mae)
        #
        # data de emissão
        c.drawString((322 + horizontal_extra), ((248.5 + vertical_extra) - sl) * mm, data_emissao)

        if count % 4 == 0 or count == len(servidores):
            c.showPage()
            count = 1
        else:
            count += 1

    c.save()

    return response
