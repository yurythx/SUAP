"""Abas do ``tabs.js`` sobre o Bootstrap 6: clique e setas ativam pelo Bootstrap, e o SUAP trata só o que é dele (ajax, ``?tab=``).

Regressão que estes testes seguram: cancelar o ``show()`` do Bootstrap para "devolver ao clique" matava a troca de painel nas abas
sem ``data-tab`` no painel, silenciava ``shown.bs.tab`` e empilhava duas entradas de histórico por clique.
"""

import re

import pytest
from playwright.sync_api import Page, expect

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

DETALHE = '/rh/servidor/7000001/'
ATIVA = re.compile(r'\bactive\b')
ABAS = '.nav-tabs .nav-link[data-bs-toggle="tab"]'
# Três painéis sem `data-tab` (como em ae/programa.html ou nas telas `abrir_processo_*`): `tabs.js` os batiza `tab0..tab2`.
PAINEIS_SEM_DATA_TAB = (
    '<div class="tab-pane" data-title="A">painel A</div><div class="tab-pane" data-title="B">painel B</div>'
    '<div class="tab-pane" data-title="C">painel C</div>'
)


def _conta_shown(page: Page) -> None:
    page.evaluate("() => { window.zzShown = []; document.addEventListener('shown.bs.tab', e => window.zzShown.push(e.target.id)); }")


def _abre_detalhe(page: Page) -> None:
    page.goto(DETALHE)
    expect(page.locator(ABAS).first).to_be_visible()
    _conta_shown(page)


def _abre_sem_data_tab(page: Page) -> None:
    page.goto('/')
    page.evaluate(
        "(html) => { const c = document.createElement('div'); c.id = 'zz-abas'; c.innerHTML = html; "
        "document.querySelector('main, #content, body').prepend(c); initTabs(0); }",
        PAINEIS_SEM_DATA_TAB,
    )
    expect(page.locator('.nav-tabs .nav-link')).to_have_count(3)
    _conta_shown(page)


def _painel_visivel(page: Page) -> str:
    return page.evaluate(
        "() => [...document.querySelectorAll('.tab-content > .tab-pane')].filter(p => getComputedStyle(p).display !== 'none').map(p => p.textContent.trim()).join('|')"
    )


def test_clique_em_aba_com_data_tab_ativa_uma_vez_e_empilha_um_historico(logado) -> None:
    page = logado('admin')
    _abre_detalhe(page)
    historico = page.evaluate('history.length')
    segunda = page.locator(ABAS).nth(1)

    segunda.click()

    expect(segunda).to_have_class(ATIVA)
    expect(page.locator(segunda.get_attribute('data-bs-target'))).to_have_css('display', 'block')
    expect(segunda).to_have_attribute('aria-selected', 'true')
    page.wait_for_function('window.zzShown.length >= 1')
    assert page.evaluate('window.zzShown') == [segunda.get_attribute('id')]
    assert page.evaluate('history.length') == historico + 1


def test_seta_em_aba_com_data_tab_ativa_uma_vez_e_empilha_um_historico(logado) -> None:
    page = logado('admin')
    _abre_detalhe(page)
    historico = page.evaluate('history.length')
    segunda = page.locator(ABAS).nth(1)
    page.locator('.nav-tabs .nav-link.active').focus()

    page.keyboard.press('ArrowRight')

    expect(segunda).to_be_focused()
    expect(segunda).to_have_class(ATIVA)
    expect(segunda).to_have_attribute('aria-selected', 'true')
    page.wait_for_function('window.zzShown.length >= 1')
    assert page.evaluate('window.zzShown') == [segunda.get_attribute('id')]
    assert page.evaluate('history.length') == historico + 1
    assert segunda.get_attribute('data-tab') in page.url


def test_clique_em_abas_sem_data_tab_troca_o_painel_e_dispara_shown_uma_vez(logado) -> None:
    page = logado('admin')
    _abre_sem_data_tab(page)
    assert _painel_visivel(page) == 'painel A'
    historico = page.evaluate('history.length')

    page.locator('.nav-tabs .nav-link', has_text='B').click()

    expect(page.locator('.tab-pane', has_text='painel B')).to_have_css('display', 'block')
    assert _painel_visivel(page) == 'painel B'
    page.wait_for_function('window.zzShown.length >= 1')
    assert page.evaluate('window.zzShown.length') == 1
    assert page.evaluate('history.length') == historico + 1


def test_seta_em_abas_sem_data_tab_ativa_o_proximo_painel_uma_vez(logado) -> None:
    page = logado('admin')
    _abre_sem_data_tab(page)
    page.locator('.nav-tabs .nav-link.active').focus()

    page.keyboard.press('ArrowRight')

    expect(page.locator('.nav-tabs .nav-link', has_text='B')).to_be_focused()
    expect(page.locator('.tab-pane', has_text='painel B')).to_have_css('display', 'block')
    assert _painel_visivel(page) == 'painel B'
    page.wait_for_function('window.zzShown.length >= 1')
    assert page.evaluate('window.zzShown.length') == 1
    page.keyboard.press('End')
    expect(page.locator('.tab-pane', has_text='painel C')).to_have_css('display', 'block')
    assert _painel_visivel(page) == 'painel C'


def test_ativar_por_trigger_de_clique_no_jquery_continua_valendo(logado) -> None:
    """As telas ``abrir_processo_*`` ativam abas com ``$('...').trigger('click')``."""
    page = logado('admin')
    _abre_sem_data_tab(page)

    page.evaluate("$('.nav-tabs .nav-link[data-bs-target$=\"tab2-tab-pane\"]').trigger('click')")

    expect(page.locator('.tab-pane', has_text='painel C')).to_have_css('display', 'block')
    assert _painel_visivel(page) == 'painel C'


def test_changetabs_direto_mantem_aria_selected_e_tabindex(logado) -> None:
    """``changeTabs(...)`` chamado direto (telas que ativam aba por código) não passa pelo ``show()`` do Bootstrap."""
    page = logado('admin')
    _abre_detalhe(page)
    abas = page.locator(ABAS)
    anterior, alvo = abas.nth(0), abas.nth(2)
    expect(anterior).to_have_class(ATIVA)

    page.evaluate('(tab) => changeTabs(tab)', alvo.get_attribute('data-tab'))

    expect(alvo).to_have_class(ATIVA)
    expect(alvo).to_have_attribute('aria-selected', 'true')
    assert alvo.evaluate('e => e.tabIndex') == 0
    expect(anterior).not_to_have_class(ATIVA)
    expect(anterior).to_have_attribute('aria-selected', 'false')
    expect(anterior).to_have_attribute('tabindex', '-1')
    expect(page.locator(alvo.get_attribute('data-bs-target'))).to_have_css('display', 'block')
    expect(page.locator(anterior.get_attribute('data-bs-target'))).to_have_css('display', 'none')


def test_aba_nao_alarga_ao_ser_selecionada(logado) -> None:
    """A aba ativa fica em negrito; a largura do negrito já vem reservada (.rotulo-aba), então selecionar não alarga nem empurra as vizinhas."""
    page = logado('admin')
    _abre_detalhe(page)
    abas = page.locator('.nav-tabs .nav-link[data-tab]')
    expect(abas.nth(2)).to_be_visible()
    larguras = lambda: abas.evaluate_all('els => els.map(e => e.getBoundingClientRect().width)')  # noqa: E731
    antes = larguras()

    abas.nth(2).click()
    expect(abas.nth(2)).to_have_class(re.compile(r'\bactive\b'))
    expect(abas.nth(2)).to_have_css('font-weight', '600')

    depois = larguras()
    assert all(abs(a - d) < 0.5 for a, d in zip(antes, depois, strict=True)), (antes, depois)
