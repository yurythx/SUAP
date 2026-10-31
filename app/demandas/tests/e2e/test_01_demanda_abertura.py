"""Fluxo: abertura de uma demanda (feature 001 do behave).

O demandante abre a demanda pelo dashboard, escolhe a área de atuação e o módulo — e a área é
o que libera os módulos, porque o formulário recarrega a lista de tags por AJAX quando ela
muda. A demanda nasce em "Solicitada" e passa a ser a âncora da cadeia: os testes seguintes
levam a mesma demanda por negociação, análise e demais etapas.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import Page, expect

from demandas.tests.e2e.apoio import marcar_modulo
from djtools.e2e_ui import Tela

if TYPE_CHECKING:
    from demandas.models import Demanda

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

DASHBOARD = '/demandas/demandas/'
LISTAGEM_ADMIN = '/admin/demandas/demanda/'
ADICIONAR_ADMIN = '/admin/demandas/demanda/add/'
VISUALIZAR = '/demandas/visualizar/{}/'

TITULO = 'Demanda 1'
DESCRICAO = 'Primeira demanda'


def demanda_da_cadeia() -> Demanda:
    """A demanda aberta por ``test_01`` — âncora dos demais arquivos da cadeia."""
    from demandas.models import Demanda

    demanda = Demanda.objects.filter(titulo=TITULO).first()
    assert demanda is not None, 'demanda ausente: a cadeia é sequencial, rode `pytest demandas/tests/e2e` inteiro'
    return demanda


def test_demandante_abre_a_demanda(logado_demandas: Callable[[str], Page]) -> None:
    """O demandante percorre o dashboard, abre a demanda e confere o registro no ORM."""
    tela = Tela(logado_demandas('demandante'))

    from demandas.models import Demanda, Situacao

    tela.ir(DASHBOARD).ver_titulo('Dashboard: Demandas').clicar_botao('Visualizar todas')
    expect(tela.pagina).to_have_url(re.compile(rf'{LISTAGEM_ADMIN}$'))
    tela.clicar_botao('Adicionar Demanda')
    expect(tela.pagina).to_have_url(re.compile(rf'{ADICIONAR_ADMIN}$'))

    # A área vem primeiro: o formulário recarrega os módulos por AJAX no `change` dela, e sem
    # essa ordem a lista de módulos fica vazia (o `__init__` do form filtra as tags pela área).
    tela.preencher('Área de Atuação', 'Autocomplete', 'Tecnologia da Informação')
    tela.preencher('Tipo', 'Radio', 'Melhoria')
    marcar_modulo(tela, 'Tag Especial')
    tela.preencher_formulario([('Título da Demanda', 'Texto', TITULO), ('Descrição da Demanda', 'TextArea', DESCRICAO)])
    tela.preencher('Demandantes', 'Autocomplete Multiplo', '105001')
    tela.clicar_botao('Salvar').sucesso('Cadastro realizado com sucesso.')

    demanda = Demanda.objects.get(titulo=TITULO)
    assert demanda.situacao == Situacao.ESTADO_ABERTO, 'a demanda nova precisa nascer em Solicitada'
    assert demanda.demandantes.filter(username='105001').exists(), 'a UI disse que salvou, mas o demandante não foi vinculado'
    assert demanda.tags.filter(nome='Tag Especial').exists(), 'a UI disse que salvou, mas o módulo não foi vinculado'


def test_visualizacao_da_demanda_pelo_demandante_e_analista(logado_demandas: Callable[[str], Page]) -> None:
    """Os dois papéis da feature abrem a demanda pela listagem do admin."""
    demanda = demanda_da_cadeia()

    demandante = Tela(logado_demandas('demandante'))
    demandante.ir(LISTAGEM_ADMIN).ver_texto(TITULO)
    demandante.linha(TITULO).clicar_icone('exibição')
    expect(demandante.pagina).to_have_url(re.compile(rf'{VISUALIZAR.format(demanda.pk)}$'))
    demandante.ver_titulo(f'Demanda {demanda.pk}: {TITULO}').ver_status('Solicitada')
    # O demandante não atende demanda: o que ele vê é o voto da solicitação, não a barra de
    # ações do analista.
    demandante.ver_botao('Concordar')

    analista = Tela(logado_demandas('analista'))
    analista.ir(LISTAGEM_ADMIN).ver_texto(TITULO)
    analista.linha(TITULO).clicar_icone('exibição')
    analista.ver_titulo(f'Demanda {demanda.pk}: {TITULO}').ver_botao('Alterar etapa')


def test_analista_vincula_se_como_responsavel(logado_demandas: Callable[[str], Page]) -> None:
    """O analista se vincula à demanda pela edição do admin e vira responsável por ela."""
    demanda = demanda_da_cadeia()
    tela = Tela(logado_demandas('analista'))

    tela.ir(f'/admin/demandas/demanda/{demanda.pk}/change/').esperar()
    tela.preencher('Analistas', 'Autocomplete Multiplo', '105002')
    tela.clicar_botao('Salvar').sucesso('Atualização realizada com sucesso.')
    demanda.refresh_from_db()
    assert demanda.analistas.filter(username='105002').exists(), 'a UI disse que atualizou, mas o analista não foi vinculado'
