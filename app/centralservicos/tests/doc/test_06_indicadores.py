"""Roteiro navegado da tarefa 12 da doc: indicadores e relatórios.

As três telas de relatório do menu Relatórios mais o Dashboard (que a tarefa 7 já mostrou para
o atendente). Todas são de leitura: o passo é escolher o período e confirmar.
"""

from __future__ import annotations

import pytest

from djtools.e2e_ui import Tela, anotar_tela

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

INDICADORES = '/centralservicos/indicadores'
ATENDIMENTOS_POR_ANO = '/centralservicos/atendimentos_por_ano/'
SITUACAO_DOS_ATENDENTES = '/centralservicos/relatorio_atendentes'


def test_acompanhar_indicadores(logado_doc, capturar):
    """Tarefa 12 — o atendente abre os indicadores e os dois relatórios do módulo.

    Quem tem ``pode_ver_indicadores`` é o grupo ``Atendente da Central de Serviços`` (e o
    ``Auditor``) — o grupo ``Gestor da Central de Serviços`` **não** concede essa permissão;
    medido na rodada (o gestor recebe 403 na tela).
    """
    tela = Tela(logado_doc('atendente')).ir(INDICADORES)
    tela.ver_titulo('Indicadores')
    anotar_tela('indicadores-form', tela)
    capturar(tela.pagina, '12-indicadores-filtros')
    tela.clicar_botao('Enviar')
    tela.ver_texto('Indicadores')
    capturar(tela.pagina, '12-indicadores')

    tela.ir(ATENDIMENTOS_POR_ANO)
    tela.ver_titulo('Relatório de Atendimentos por Ano')
    anotar_tela('atendimentos-por-ano-form', tela)
    tela.clicar_botao('Enviar')
    tela.ver_texto('Relatório de Atendimentos por Ano')
    capturar(tela.pagina, '12-atendimentos-por-ano')

    tela.ir(SITUACAO_DOS_ATENDENTES)
    tela.ver_titulo('Relatório de Situação dos Atendentes')
    anotar_tela('situacao-atendentes-form', tela)
    tela.clicar_botao('Enviar')
    tela.ver_texto('Relatório de Situação dos Atendentes')
    capturar(tela.pagina, '12-situacao-dos-atendentes')
