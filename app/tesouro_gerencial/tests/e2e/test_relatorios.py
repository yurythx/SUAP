"""Fluxo: os dois relatórios das variáveis financeiras, sobre a execução de referência do campus ``TGE``.

As onze variáveis (``Variavel`` em ``tesouro_gerencial/models.py``) são o produto do módulo: alimentam
a matriz orçamentária, e cada uma é uma regra diferente de inclusão e exclusão sobre os mesmos
documentos. A execução de referência (``_semear_execucao_de_referencia`` no conftest) tem uma parcela
reconhecível de cada fonte — liquidação de empenho LOA (4.000), de empenho de destaque (250), resto a
pagar (700), nota de crédito (300) e receita de GRU (1.500) — e a tabela ``TOTAIS`` abaixo é a regra de
cada variável escrita como resultado: LOA não soma destaque, as ``f*`` somam os dois, GCC só pega
contrato continuado (natureza 339039, subitem 17) e deixa a nota de crédito de fora, RECCAPT é só GRU.

Regressão que pega: uma mudança em qualquer filtro de ``Variavel`` muda um total desta tabela; a troca
de UG por UGR (``CODIGO_UG``/``CODIGO_UGR`` são diferentes de propósito) zera a variável errada.
"""

import pytest

from djtools.e2e_ui import Tela
from tesouro_gerencial.tests.e2e.conftest import ANO_REFERENCIA, CODIGO_UGR, EMPENHO_DESTAQUE, EMPENHO_LOA, NOME_CAMPUS, SIGLA_CAMPUS

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

VARIAVEIS = '/tesouro_gerencial/variaveis/'
CAMPI = '/tesouro_gerencial/campi/'

RESTO_A_PAGAR = f'{ANO_REFERENCIA - 1}NE000555'
NOTA_DE_CREDITO = f'{ANO_REFERENCIA}NC000101'

# Variável -> total do campus `TGE` em `ANO_REFERENCIA`.
TOTAIS = {
    'DEST_EXEC': '250,00',  # só o empenho de outra unidade orçamentária
    'LOA_EXEC': '5.000,00',  # 4.000 + 700 + 300: LOA do IFRN, sem o destaque
    'RECCAPT': '1.500,00',  # só a receita de GRU
    '20RL_LOA': '5.000,00',  # tudo na ação 20RL
    'GCC': '4.700,00',  # empenho + resto a pagar de contrato continuado; nota de crédito não entra
    'GTO_LOA': '5.000,00',
    'fGPE': '0,00',  # gasto com pessoal: folha (vazia aqui); empenho só na reitoria
    'fGTO': '5.250,00',  # gastos totais: LOA + destaque
    'fGOC': '5.250,00',
    'fGCI': '0,00',  # investimento (grupo 4): nada no seed
    'fGCO': '5.250,00',
}


def test_variaveis_por_campus_somam_a_execucao_do_campus(logado_tesouro):
    """O gestor escolhe campus e ano e vê, numa aba por variável, o total e o que o compõe."""
    tela = Tela(logado_tesouro('gestor')).ir(VARIAVEIS)
    tela.ver_titulo('Relatório de Variáveis por Campus')
    tela.preencher_formulario([('Campus', 'autocomplete', SIGLA_CAMPUS), ('Ano', 'número', str(ANO_REFERENCIA))])
    tela.clicar_botao('Enviar')

    for variavel, total in TOTAIS.items():
        tela.clicar_aba(variavel)
        tela.aba(variavel).ver_texto(f'R$ {total}')

    tela.clicar_aba('LOA_EXEC')
    loa = tela.aba('LOA_EXEC')
    loa.linha(EMPENHO_LOA).ver_texto('4.000,00')  # o empenho entra pelo valor LIQUIDADO, não pelo empenhado (8.000)
    loa.linha(RESTO_A_PAGAR).ver_texto('700,00')
    loa.linha(NOTA_DE_CREDITO).ver_texto('300,00')

    tela.clicar_aba('DEST_EXEC')
    tela.aba('DEST_EXEC').linha(EMPENHO_DESTAQUE).ver_texto('250,00')


def test_campi_por_variavel_mostra_o_total_de_cada_campus(logado_tesouro):
    """Uma variável, todos os campi: cada campus é um quadro recolhido, com o total e os documentos."""
    tela = Tela(logado_tesouro('gestor')).ir(CAMPI)
    tela.ver_titulo('Relatório de Campi por Variável')
    tela.preencher_formulario([('Variável', 'lista', 'LOA_EXEC'), ('Ano', 'número', str(ANO_REFERENCIA))])
    tela.clicar_botao('Enviar')

    campus = f'{CODIGO_UGR} {NOME_CAMPUS}'  # o quadro identifica o campus pela UGR, não pela sigla
    tela.clicar_botao(campus)
    quadro = tela.quadro(campus)
    quadro.ver_texto(f'R$ {TOTAIS["LOA_EXEC"]}')
    quadro.linha(EMPENHO_LOA).ver_texto('4.000,00')
    quadro.linha(RESTO_A_PAGAR).ver_texto('700,00')
    quadro.linha(NOTA_DE_CREDITO).ver_texto('300,00')
