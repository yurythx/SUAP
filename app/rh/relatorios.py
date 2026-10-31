from datetime import datetime
from os.path import join

from django.conf import settings
from django.utils import dateformat

from comum.models import Configuracao
from djtools.relatorios.reportlabplus import Image, PdfReport, para, space, table


def get_recadastramento_pdf(request):
    def coluna(chave, fontSize='10', alignment='left'):
        if chave in request.POST:
            return para(
                '<para fontSize="{}" alignment="{}">{}</para>'.format(
                    fontSize, alignment, [request.POST[chave] if request.POST[chave] != 'None' else ' '][0]
                ),
                escape=False,
            )
        return para(f'<para fontSize="{fontSize}" alignment="{alignment}"><b>{chave}</b></para>', escape=False)

    def insere(rows, colWidths, tabela):
        if rows and colWidths:
            tabela.append({'rows': [rows], 'colWidths': colWidths})
        else:
            tabela.append(None)

    tabela = []

    if 'instituidor_matricula' in request.POST:
        rec = 'Pensionista'
    else:
        rec = 'Aposentado'

    img1 = Image(join(settings.STATIC_ROOT, 'comum/img/brasao_cinza.jpg'), width=40, height=40)
    img2 = Image(join(settings.STATIC_ROOT, 'comum/img/simbolo_ifrn.jpg'), width=40, height=40)
    cabecalho = '<para alignment="center">MINISTÉRIO DA EDUCAÇÃO'
    cabecalho += f'<br />INSTITUTO FEDERAL DE EDUCAÇÃO, CIÊNCIA E TECNOLOGIA DO {Configuracao.get_valor_por_chave("comum", "instituicao_estado")}'
    cabecalho += '<br />CNPJ 10.877.412/0001-68'
    cabecalho += f'<br />Atualização Cadastral {datetime.now().year} ({rec})</para>'

    insere([img1, para(cabecalho, escape=False), img2], [20, 150, 20], tabela)
    insere(None, None, tabela)
    insere([coluna('Decreto Nº 7.141 de 29 de março de 2010.', alignment='center')], [190], tabela)
    insere(None, None, tabela)
    insere([coluna('DADOS BÁSICOS')], [190], tabela)

    if rec == 'Pensionista':
        insere([coluna('Matricula'), coluna('Nome do Intituidor de Pensão')], [30, 160], tabela)
        insere([coluna('instituidor_matricula'), coluna('instituidor_nome')], [30, 160], tabela)
    insere([coluna('Matricula'), coluna(f'Nome do {rec}'), coluna('Nascimento')], [30, 130, 30], tabela)
    insere([coluna('matricula'), coluna('nome'), coluna('nascimento_data')], [30, 130, 30], tabela)
    insere([coluna('Filiação')], [190], tabela)
    insere([coluna('nome_mae')], [190], tabela)
    insere([coluna('nome_pai')], [190], tabela)
    insere(
        [coluna('CPF'), coluna('RG'), coluna('Órgão'), coluna('Emissão'), coluna('Título'), coluna('Zona'), coluna('Seção'), coluna('UF')],
        [30, 30, 30, 30, 25, 15, 15, 15],
        tabela,
    )
    insere(
        [
            coluna('cpf'),
            coluna('rg'),
            coluna('rg_orgao'),
            coluna('rg_data'),
            coluna('titulo_numero'),
            coluna('titulo_zona'),
            coluna('titulo_secao'),
            coluna('titulo_uf'),
        ],
        [30, 30, 30, 30, 25, 15, 15, 15],
        tabela,
    )
    insere([coluna('Endereço')], [190], tabela)
    insere([coluna('enderecos')], [190], tabela)
    insere([coluna('Telefone'), coluna('Sexo'), coluna('Estado Civil')], [140, 25, 25], tabela)
    insere([coluna('telefones'), coluna('sexo'), coluna('estado_civil')], [140, 25, 25], tabela)
    insere([coluna('Banco'), coluna('Agência'), coluna('Conta Corrente')], [140, 25, 25], tabela)
    insere([coluna('pagto_banco'), coluna('pagto_agencia'), coluna('pagto_ccor')], [140, 25, 25], tabela)
    insere(None, None, tabela)

    insere([coluna('DADOS REPRESENTANTE LEGAL')], [190], tabela)
    insere([coluna('Nome do Representante')], [190], tabela)
    insere([coluna(' ')], [190], tabela)
    insere([coluna('CPF'), coluna('RG'), coluna('Órgão'), coluna('Emissão')], [50, 50, 45, 45], tabela)
    insere([coluna(' '), coluna(' '), coluna(' '), coluna(' ')], [50, 50, 45, 45], tabela)
    insere([coluna('Endereço')], [190], tabela)
    insere([coluna(' ')], [190], tabela)
    insere([coluna('Cidade'), coluna('UF'), coluna('CEP'), coluna('Telefone')], [80, 10, 20, 80], tabela)
    insere([coluna(' '), coluna(' '), coluna(' '), coluna(' ')], [80, 10, 20, 80], tabela)
    insere([coluna('Cartório'), coluna('Livro'), coluna('Folha'), coluna('Validade')], [65, 30, 30, 65], tabela)
    insere([coluna(' '), coluna(' '), coluna(' '), coluna(' ')], [65, 30, 30, 65], tabela)
    insere(None, None, tabela)
    data = dateformat.format(datetime.now(), r'j \d\e F \d\e Y')

    assinatura = '<para fontSize="10" alignment="center">Declaro, sob as penas da Lei, '
    assinatura += 'que os dados informados neste formulário correspondem à expressão da verdade.<br /><br />'
    assinatura += '____________________________________________________________<br />'
    assinatura += f'Assinatura do {rec} ou Representante Legal<br /><br />'
    assinatura += '____________________________________________________________<br />'
    assinatura += f'{request.user.get_profile().servidor.matricula} - {request.user.get_profile().servidor.pessoa_fisica.nome}<br />'
    assinatura += (
        f'{Configuracao.get_valor_por_chave("comum", "municipio_sede")}/{Configuracao.get_valor_por_chave("comum", "instituicao_estado")}, %s<br /><br /></para>'
        % data
    )
    insere([para(assinatura, escape=False)], [190], tabela)
    insere(None, None, tabela)
    instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
    insere([coluna(f'COMPROVANTE DE ATUALIZAÇÃO CADASTRAL DE {rec.upper()} - {instituicao} - {datetime.now().year}')], [190], tabela)
    comprovante = '<para fontSize="10" alignment="center">'
    comprovante += 'O(a) {}(a) {} atualizou seus dados em {}.<br /><br />'.format(rec, request.POST['nome'], data)
    comprovante += '____________________________________________________________<br />'
    comprovante += f'{request.user.get_relacionamento().matricula} - {request.user.get_profile().nome} (Assinatura e Carimbo)<br /><br /></para>'
    observacao = '<para fontSize="6" alignment="left">'
    observacao += 'A atualização cadastral dos servidores aposentados e dos pensionistas da '
    observacao += 'União que recebem proventos ou pensão à conta do Tesouro Nacional será '
    observacao += 'realizada anualmente pelos órgãos e entidades da Administração Pública '
    observacao += 'Federal direta, autárquica e fundacional no mês de aniversário do aposentado '
    observacao += 'ou pensionista. Os aposentados e pensionistas que não se apresentarem para fins '
    observacao += 'de atualização cadastral terão seus vencimentos suspensos.</para>'
    insere([para(comprovante, escape=False)], [190], tabela)
    insere([para(observacao, escape=False)], [190], tabela)

    doc = PdfReport(body=[space(3) if item is None else table(rows=item['rows'], w=item['colWidths']) for item in tabela])

    return doc
