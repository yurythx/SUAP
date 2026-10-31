"""Menu lateral da fase 3a da modernização, numa tela real (tema Padrão).

Spec: ``docs/superpowers/specs/2026-10-16-modernizacao-fase3a-menu-design.md``.
"""

import re

import pytest
from playwright.sync_api import Locator, Page, expect

from tests.e2e.test_tema_visual import _token

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

PAGINA = '/admin/rh/pessoajuridica/'
MENU = '#mainmenu > ul._main_menu'  # o `nav` tem também a lista da busca, oculta


def _vai(page: Page, url: str) -> None:
    """Abre a página como em produção: ``settings_test`` usa DEBUG=True e ``body.debug`` pinta a barra com ``--debug-color``;
    sem transição, para ler o estilo final (``aside`` tem ``transition: all``)."""
    page.emulate_media(reduced_motion='reduce')
    page.goto(url)
    page.evaluate("document.body.classList.remove('debug')")


def _abrir_pagina_pelo_menu(page: Page) -> Locator:
    """Segue um subitem do menu pelo ``breadcrumbs_reset``, que grava ``menu_item_id`` na sessão: o ``open_menu_item`` só marca
    a página atual (``li.active`` e ``aria-current="page"``) assim. Sob pytest o menu emite o href direto, sem o desvio
    (``running_tests`` em ``djtools/menu.py``), então o teste monta o mesmo caminho. Devolve o link da página atual."""
    _vai(page, PAGINA)
    subitem = page.locator(f'{MENU} > li.has-child > ul > li[id]').first  # subitem direto de uma categoria (2º nível)
    item_id = subitem.get_attribute('id').removeprefix('menu-item-')
    href = subitem.locator(':scope > a').get_attribute('href')
    _vai(page, f'/djtools/breadcrumbs_reset/{item_id}{href}')
    atual = page.locator(f'{MENU} a[aria-current="page"]')
    expect(atual).to_have_count(1)
    return atual


def test_barra_escura_e_pagina_atual_com_fundo_e_texto_teal(logado) -> None:
    page = logado('admin')
    atual = _abrir_pagina_pelo_menu(page)
    expect(page.locator('aside.nav')).to_have_css('background-color', _token(page, '--grey-900'))
    expect(atual).to_have_css('color', _token(page, '--primary-400'))
    expect(atual).to_have_css('background-color', _token(page, '--grey-800'))
    expect(atual).to_have_css('font-weight', '600')
    expect(atual).to_have_css('box-shadow', 'none')  # sem a barrinha teal que o usuário rejeitou
    expect(page.locator('header #user-tools .minha-conta')).to_have_css('border-radius', '10px')


def test_homologacao_troca_os_cinzas_do_menu_por_vermelhos_escuros(logado) -> None:
    """Em homologação (``body.debug``) a barra é ``--debug-color``: página atual e busca não ficam cinzas sobre o vermelho."""
    page = logado('admin')
    atual = _abrir_pagina_pelo_menu(page)
    page.evaluate("document.body.classList.add('debug')")
    expect(page.locator('aside.nav')).to_have_css('background-color', _token(page, '--danger-800'))
    expect(atual).to_have_css('background-color', _token(page, '--danger-900'))
    expect(page.locator(f'{MENU} > li.opened > a').first).to_have_css('background-color', _token(page, '--danger-900'))
    busca = page.locator('aside.nav .buscar_menu input[type=search]')
    expect(busca).to_have_css('background-color', _token(page, '--danger-850'))
    expect(busca).to_have_css('border-top-color', _token(page, '--grey-500'))


def test_categoria_aberta_com_fundo_e_subitens_sem_traco(logado) -> None:
    page = logado('admin')
    _abrir_pagina_pelo_menu(page)
    aberta = page.locator(f'{MENU} > li.opened > a').first
    expect(aberta).to_have_css('background-color', _token(page, '--grey-800'))
    expect(aberta).to_have_css('border-radius', '10px')
    sub = page.locator(f'{MENU} > li.opened li').first
    expect(sub).to_have_css('border-bottom-style', 'none')
    expect(page.locator(f'{MENU} > li.opened > ul').first).to_have_css('border-left-color', _token(page, '--grey-750'))


def test_4o_nivel_do_menu_segue_a_cor_de_subitem(logado) -> None:
    """Do 3º nível em diante o link tem a cor de subitem: o 4º nível não fica mais claro que o pai (o clássico escalona 200/300/400)."""
    page = logado('admin')
    _vai(page, PAGINA)
    link = page.locator(f'{MENU} > li > ul > li > ul > li > ul > li > a').first  # 4º nível
    expect(link).to_have_count(1)
    link.evaluate(
        """a => { for (let li = a.closest('li'); li && li.closest('#mainmenu'); li = li.parentElement.closest('li')) {
            li.classList.add('opened'); const ul = li.querySelector(':scope > ul'); if (ul) ul.style.display = 'block'; } }"""
    )
    expect(link).to_be_visible()
    expect(link).to_have_css('color', _token(page, '--grey-300'))


def test_hover_de_item_ganha_fundo(logado) -> None:
    page = logado('admin')
    _vai(page, PAGINA)
    item = page.locator(f'{MENU} > li.menu-inicio > a')
    item.hover()
    expect(item).to_have_css('background-color', _token(page, '--grey-850'))
    expect(item).to_have_css('color', _token(page, '--white'))


def test_foco_por_teclado_visivel_no_item_atual(logado) -> None:
    page = logado('admin')
    atual = _abrir_pagina_pelo_menu(page)
    atual.focus()  # Playwright foca como teclado: :focus-visible casa
    expect(atual).to_have_css('outline-style', 'solid')
    expect(atual).to_have_css('outline-color', _token(page, '--primary-400'))  # currentColor


def test_busca_do_menu_preenchida_arredondada_e_sem_anel(logado) -> None:
    page = logado('admin')
    _vai(page, PAGINA)
    busca = page.locator('aside.nav .buscar_menu input[type=search]')
    expect(busca).to_have_css('background-color', _token(page, '--grey-850'))
    expect(busca).to_have_css('border-radius', '10px')
    expect(busca).to_have_css('border-top-color', _token(page, '--grey-600'))
    expect(busca).to_have_css('height', '38px')
    busca.focus()
    expect(busca).to_have_css('box-shadow', 'none')  # sem o anel claro da fase 2
    expect(busca).to_have_css('color', _token(page, '--white'))
    expect(busca).to_have_css('border-top-color', _token(page, '--grey-400'))


def test_menu_retraido_marca_a_categoria_da_pagina_atual(logado) -> None:
    page = logado('admin')
    _abrir_pagina_pelo_menu(page)
    try:
        page.locator('#toggleSidebar').click()
        expect(page.locator('body')).to_have_class(re.compile(r'\bhideSidebar\b'))
        pai = page.locator('#mainmenu > ul > li.active > a').first
        expect(pai).to_have_css('background-color', _token(page, '--grey-800'))
        expect(pai.locator('.icone')).to_have_css('color', _token(page, '--primary-300'))
        expect(pai).to_have_css('justify-content', 'center')
    finally:
        page.request.get('/comum/expandir_menu/')


def test_barra_do_celular_escura_neutra_e_sino_vermelho(logado) -> None:
    page = logado('admin')
    page.set_viewport_size({'width': 390, 'height': 844})
    _vai(page, PAGINA)
    barra = page.locator('#mobilemenu')
    expect(barra).to_have_css('background-color', _token(page, '--grey-900'))
    expect(barra).to_have_css('border-top-left-radius', '18px')
    expect(barra.locator('a[href="/"]')).to_have_css('color', _token(page, '--grey-200'))
    expect(barra.locator('a.error')).to_have_css('color', _token(page, '--danger'))


@pytest.mark.parametrize('movimento', ['no-preference', 'reduce'])
def test_celular_com_menu_fechado_sem_faixa_escura(logado, movimento: str) -> None:
    """A faixa era a barra nascendo aberta (270 px sobre a página) e encolhendo (``transition: all``) quando o ``hideSidebar`` só
    chegava no ``ready`` do ``base.html``. O medidor anota a maior largura do ``aside.nav`` em todo quadro desde o início da página."""
    page = logado('admin')
    page.set_viewport_size({'width': 390, 'height': 844})
    page.emulate_media(reduced_motion=movimento)
    page.add_init_script(
        """(() => { window.__larguraMaxima = 0;
        const mede = () => { const a = document.querySelector('aside.nav');
            if (a) window.__larguraMaxima = Math.max(window.__larguraMaxima, a.getBoundingClientRect().width);
            requestAnimationFrame(mede); };
        requestAnimationFrame(mede); })()"""
    )
    page.goto(PAGINA)
    expect(page.locator('body')).to_have_class(re.compile(r'\bhideSidebar\b'))
    page.wait_for_timeout(700)  # mais que os 500 ms do transition: o medidor viu todos os quadros do encolhimento
    assert page.evaluate('window.__larguraMaxima') == 0
    assert page.locator('main#content').evaluate('e => e.getBoundingClientRect().left') == 0
