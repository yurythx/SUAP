"""Filtros de campus e setor dono da listagem de documentos (#16372).

O filtro de setor depende do de campus: escolhido um campus, só oferece os setores dele; limpo o
campus, volta a oferecer os setores de todos os campi — na hora, sem precisar clicar em "Filtrar".
Antes, a lista de setores só mudava ao filtrar: depois de filtrar por um campus e limpá-lo, o
filtro de setor continuava preso aos setores do campus anterior.
"""

import pytest
from playwright.sync_api import Page, expect

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

LISTAGEM = '/admin/documento_eletronico/documentotexto/?opcao=1'
CAMPUS = '#setor_donouo_select'
SETOR = '#setor_dono_select'
SETORES_CEN = ['Todos', 'CEN', 'DIAC/CEN', 'DIDE/CEN']
TODOS_OS_SETORES = [*SETORES_CEN, 'RAIZ']


def _setores(pagina: Page) -> list[str]:
    return pagina.locator(f'{SETOR} option').evaluate_all('opcoes => opcoes.map(o => o.textContent.trim())')


def _filtrar(pagina: Page) -> None:
    with pagina.expect_response(lambda resposta: 'documentotexto/?' in resposta.url):
        pagina.click('#button_filter')
    expect(pagina.locator(SETOR)).to_be_attached()


def test_setores_acompanham_o_campus_escolhido_e_o_campus_limpo(logado_documento) -> None:
    pagina = Tela(logado_documento('gerente')).ir(LISTAGEM).pagina
    assert _setores(pagina) == TODOS_OS_SETORES

    pagina.select_option(CAMPUS, label='CEN', force=True)
    assert _setores(pagina) == SETORES_CEN

    _filtrar(pagina)
    assert 'setor_donouo=' in pagina.url
    assert _setores(pagina) == SETORES_CEN

    # O "x" do select2 limpa o campus: os setores dos demais campi voltam sem refiltrar.
    pagina.locator(f'{CAMPUS} + .select2 .select2-selection__clear').click()
    assert _setores(pagina) == TODOS_OS_SETORES

    _filtrar(pagina)
    assert 'setor_donouo=' not in pagina.url
    assert _setores(pagina) == TODOS_OS_SETORES

    # Setor escolhido que não é do novo campus volta para "Todos".
    pagina.select_option(SETOR, label='DIDE/CEN', force=True)
    pagina.select_option(CAMPUS, label='RAIZ', force=True)
    assert _setores(pagina) == ['Todos', 'RAIZ']
    assert pagina.locator(SETOR).input_value() == ''
