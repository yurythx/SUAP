from os.path import join

from django.apps import apps
from django.conf import settings

from djtools import relatorios


def get_topo_com_titulo(titulo=''):
    # Deve ser utilizado com papel A4
    image_path = join(settings.STATIC_ROOT, 'comum/img/brasao_cinza.jpg')
    image = relatorios.Image(image_path, width=15.96 * relatorios.mm, height=17.4 * relatorios.mm)
    instituicao = apps.get_model('comum', 'configuracao').get_valor_por_chave('comum', 'instituicao')
    para = relatorios.para(f'{instituicao}<br/><b>{titulo}</b>', align='center', escape=False)
    tabela_imagem = relatorios.table([[image, para]], w=[25, 165], grid=0)
    return [tabela_imagem, relatorios.space(5)]


def rodape_data_e_assinatura(assinatura='Coordenação do Patrimonio'):
    """
    Retorna um rodapé para ser inserido em pdf do tipo:

    Natal, ___ de ______________________ de ______

    ______________________________________________
             Coordenação do Patrimônio

    """
    return {
        'height': 30,
        'story': [
            relatorios.para(
                '<font size=9>_______________________, ______ de __________________________ de ____________</font>', alignment='center', escape=False
            ),
            relatorios.space(7),
            relatorios.para('_________________________________________________', alignment='center'),
            relatorios.table([[assinatura]], grid=0, w=[145], a=['c'], blank=''),
        ],
    }


def rodape_data_e_duas_assinaturas(assinaturas=None):
    """
    Retorna um rodapé para ser inserido em pdf do tipo:

                                     Natal, ___ de ______________________ de ______

    ______________________________________________                   ______________________________________________
             Coordenação do Patrimônio                                           Coordenação do Patrimônio

    """
    if assinaturas is None:
        assinaturas = ['Coordenação do Almoxarifado', 'Natercio Dias de Holanda']
    tabela_campos_assinaturas = [['___________________________________', ' ', '___________________________________']]
    tabela_assinaturas = [[assinaturas[0], '  ', assinaturas[1]]]
    return {
        'height': 50,
        'story': [
            relatorios.para(
                '<font size=9>Documento assinado digitalmente por meio de login e senha do SUAP</font>', alignment='center', escape=False
            ),
            relatorios.space(7),
            relatorios.table(tabela_campos_assinaturas, w=[60, 40, 60], grid=0, a=['l', 'c', 'r'], escape=False),
            relatorios.table(tabela_assinaturas, w=[60, 40, 61], grid=0, a=['c', 'c', 'c'], escape=False),
        ],
    }


def rodape_data_e_duas_assinaturas_almoxarifado(assinaturas=None):
    if assinaturas is None:
        assinaturas = ['Coordenação do Almoxarifado', 'Natercio Dias de Holanda']
    tabela_dados_assinaturas = [['Fornecedor', ' ', 'Solicitante']]
    tabela_campos_assinaturas = [['___________________________________', ' ', '___________________________________']]

    if assinaturas[6] == 'user':
        tabela_mensagem = [['  ', '   ', '    ']]
    else:
        tabela_mensagem = [['Documento assinado digitalmente por meio de login e senha do SUAP.', ' ', ' ']]
    tabela_campus = [[assinaturas[4], ' ', assinaturas[5]]]
    tabela_matricula = [['Matrícula', assinaturas[1], ' ', 'Matrícula', assinaturas[3]]]
    tabela_assinaturas = [[assinaturas[0], '  ', assinaturas[2]]]
    return {
        'height': 50,
        'story': [
            relatorios.table(tabela_dados_assinaturas, w=[60, 40, 60], grid=0, a=['l', 'c', 'l']),
            relatorios.space(5),
            relatorios.table(tabela_campos_assinaturas, w=[60, 40, 60], grid=0, a=['l', 'c', 'l']),
            relatorios.table(tabela_assinaturas, w=[60, 40, 60], grid=0, a=['l', 'c', 'l']),
            relatorios.table(tabela_campus, w=[60, 40, 60], grid=0, a=['l', 'l', 'l']),
            relatorios.table(tabela_matricula, w=[17, 23, 60, 17, 43], grid=0, a=['l', 'l', 'l', 'l', 'l']),
            relatorios.space(7),
            relatorios.table(tabela_mensagem, w=[100, 40, 20], grid=0, a=['l', 'c', 'l']),
        ],
    }
