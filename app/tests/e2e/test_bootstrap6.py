"""Comportamento do SUAP sobre o Bootstrap 6 (abas, teclado e Menu), numa tela real (tema Padrão).

O Bootstrap 6 pôs os componentes em ``@layer`` e trocou o dropdown pelo Menu: as regras do tema, que não estão em camada, passam a
vencer as do Bootstrap, e o JS só registra o teclado na instância do componente.
"""

import hashlib
import re
import subprocess
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.test_tema_visual import _token

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

DETALHE = '/rh/servidor/7000001/'
INICIO = '/'
ATIVA = re.compile(r'\bactive\b')
ABAS = '.nav-tabs .nav-link[data-bs-toggle="tab"]'


def _abre_detalhe(page: Page) -> None:
    page.goto(DETALHE)
    expect(page.locator(ABAS).first).to_be_visible()


def test_aba_inativa_fica_oculta_e_a_ativa_aparece(logado) -> None:
    page = logado('admin')
    _abre_detalhe(page)

    ativa = page.locator('.tab-content > .tab-pane.active')
    expect(ativa).to_have_count(1)
    expect(ativa).to_have_css('display', 'block')
    inativas = page.locator('.tab-content > .tab-pane:not(.active)')
    assert inativas.count() > 1
    for i in range(inativas.count()):
        expect(inativas.nth(i)).to_have_css('display', 'none')


def test_ul_nav_sem_recuo_e_nav_link_em_bloco(logado) -> None:
    page = logado('admin')
    _abre_detalhe(page)

    expect(page.locator('ul.nav.nav-tabs').first).to_have_css('padding-left', '0px')
    expect(page.locator(ABAS).first).to_have_css('display', 'block')


def test_seta_para_a_direita_move_o_foco_e_troca_de_aba(logado) -> None:
    page = logado('admin')
    _abre_detalhe(page)
    abas = page.locator(ABAS)
    primeira, segunda = abas.nth(0), abas.nth(1)

    page.locator('.nav-tabs .nav-link.active').focus()
    page.keyboard.press('ArrowRight')

    expect(segunda).to_be_focused()
    expect(segunda).to_have_class(ATIVA)
    alvo = segunda.get_attribute('data-bs-target')
    expect(page.locator(alvo)).to_have_css('display', 'block')
    expect(primeira).not_to_have_class(ATIVA)
    expect(page.locator(primeira.get_attribute('data-bs-target'))).to_have_css('display', 'none')


def test_menu_do_quadro_abre_e_seta_para_baixo_move_o_foco(logado) -> None:
    page = logado('admin')
    page.goto(INICIO)
    toggle = page.locator('.portlet-header [data-bs-toggle="menu"]').first
    expect(toggle).to_be_visible()
    toggle.click()
    menu = page.locator('.portlet-header .menu.show').first
    expect(menu).to_be_visible()

    page.keyboard.press('ArrowDown')

    foco = page.locator('.menu.show .menu-item:focus')
    expect(foco).to_have_count(1)


def test_menu_de_documentos_na_listagem_real_do_rsc_abre_ao_alcance(logado, sync_permissions) -> None:
    """Na listagem de verdade (``td`` de tabela, wrapper ``position: static``): o menu abre colado ao botão, dentro da tela, e o item recebe o clique."""
    from rh.models import Servidor
    from rsc.models import ProcessoRSC
    from rsc.tests.factories import ProcessoRSCFactory

    ProcessoRSCFactory(servidor=Servidor.objects.get(matricula='7000001'), status=ProcessoRSC.STATUS_AGUARDANDO_AVALIADORES)
    page = logado('admin')
    page.goto('/admin/rsc/processorsc/')
    toggle = page.locator('td [data-bs-toggle="menu"]').first
    toggle.click()
    menu = page.locator('td .menu.show').first
    expect(menu).to_be_visible()

    caixa, botao, tela = menu.bounding_box(), toggle.bounding_box(), page.viewport_size
    assert caixa['x'] >= 0
    assert caixa['x'] + caixa['width'] <= tela['width']
    abaixo = abs(caixa['y'] - (botao['y'] + botao['height']))
    acima = abs(caixa['y'] + caixa['height'] - botao['y'])
    assert min(abaixo, acima) < 20, 'o menu abriu longe do botão'  # o Popper inverte para cima se faltar espaço embaixo
    item = menu.locator('.menu-item').first
    assert item.evaluate(
        'e => { const r = e.getBoundingClientRect(); return e.contains(document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2)); }'
    )


@pytest.mark.parametrize('origem', ['rsc', 'rsc_tae', 'professor_titular'])
def test_menu_de_acoes_gerado_em_python_abre(logado, origem: str) -> None:
    """O HTML sai das próprias ``ModelAdmin`` (o mesmo código que monta as colunas da listagem) e é posto numa tela real."""
    html = _html_do_admin(origem)
    page = logado('admin')
    page.goto(INICIO)
    page.evaluate(
        "(html) => document.querySelector('main, #content, body').insertAdjacentHTML('afterbegin', `<div id=\"zz-menu\">${html}</div>`)", html
    )

    toggle = page.locator('#zz-menu [data-bs-toggle="menu"]')
    expect(toggle).to_be_visible()
    toggle.click()
    expect(page.locator('#zz-menu .menu.show')).to_be_visible()
    assert page.locator('#zz-menu [data-bs-toggle="dropdown"]').count() == 0
    page.keyboard.press('ArrowDown')
    expect(page.locator('#zz-menu .menu-item:focus')).to_have_count(1)


def _html_do_admin(origem: str) -> str:
    from django.contrib import admin

    if origem == 'rsc':
        from rsc.admin import ProcessoRSCAdmin
        from rsc.models import ProcessoRSC

        processo = ProcessoRSC(id=1, status=ProcessoRSC.STATUS_AGUARDANDO_AVALIADORES)
        return str(ProcessoRSCAdmin(ProcessoRSC, admin.site).botao_imprimir(processo))
    if origem == 'rsc_tae':
        from rsc_tae.admin.processo import ProcessoRSCTaeAdmin
        from rsc_tae.models import ProcessoRSCTae

        itens = [{'url': '/a/', 'label': 'Uma'}, {'url': '/b/', 'label': 'Outra'}]
        return str(ProcessoRSCTaeAdmin(ProcessoRSCTae, admin.site)._html_dropdown(itens))
    from professor_titular.admin import ProcessoTitularAdmin
    from professor_titular.models import ProcessoTitular

    processo = ProcessoTitular(id=1, status=ProcessoTitular.STATUS_AGUARDANDO_AVALIADORES)
    return str(ProcessoTitularAdmin(ProcessoTitular, admin.site).botao_imprimir(processo))


# --- Aparência: o que o Bootstrap 6 mudou sob regras do tema (utilitários, caixa, Menu, distintivo, :root) ---

GUIA = '/comum/design_system/'


def _abre_guia(page: Page, aba: str) -> None:
    """Abre uma aba do guia de design e expande as caixas dela (vêm recolhidas)."""
    page.goto(f'{GUIA}?tab={aba}')
    page.evaluate("(aba) => document.querySelectorAll(`#${aba}-tab-pane .accordion-collapse`).forEach(e => e.classList.add('show'))", aba)


def test_utilitarios_de_alinhamento_vencem_a_regra_de_elemento_do_tema(logado) -> None:
    """``table thead th { text-align: left }`` do tema perdia do ``.text-center`` do 6 (em camada, sem ``!important``)."""
    page = logado('admin')
    _abre_guia(page, 'tabelas_e_listas')

    expect(page.locator('table.logotipos thead th.text-center').first).to_have_css('text-align', 'center')
    expect(page.locator('#tabelas_e_listas-tab-pane td.text-end').first).to_have_css('text-align', 'right')


def test_escala_de_espacamento_do_bootstrap_5(logado) -> None:
    """No 5 ``mt-4`` era 1,5rem (a escala do 6 deu 0,75rem) e ``gap-5`` 3rem."""
    page = logado('admin')
    _abre_guia(page, 'tabelas_e_listas')
    expect(page.locator('#tabelas_e_listas-tab-pane dl.definition-list.mt-4').first).to_have_css('margin-top', '15px')

    page.evaluate(
        '() => document.body.insertAdjacentHTML(\'beforeend\', \'<div id="zz-gap" class="d-flex gap-5"><i></i><i></i></div><div id="zz-col" class="row"><div class="col-md-6">a</div></div>\')'
    )
    expect(page.locator('#zz-gap')).to_have_css('column-gap', '30px')
    page.set_viewport_size({'width': 1280, 'height': 800})
    assert page.locator('#zz-col .col-md-6').evaluate('e => e.getBoundingClientRect().width / e.parentElement.getBoundingClientRect().width') > 0.45


def test_caixa_mantem_titulo_corpo_e_estouro_do_bootstrap_5(logado) -> None:
    page = logado('admin')
    _abre_guia(page, 'caixas_secoes')
    painel = page.locator('#caixas_secoes-tab-pane')

    expect(painel.locator('h2.accordion-header').first).to_have_css('font-size', '20px')
    expect(painel.locator('.accordion-body').first).to_have_css('font-size', '13px')
    expect(painel.locator('.accordion-collapse.show').first).to_have_css('overflow-y', 'visible')
    # Caixa fechada: o fundo é o do tema (transparente no Padrão), não o branco que o 6 põe no botão.
    expect(painel.locator('.accordion-button.collapsed').first).to_have_css('background-color', 'rgba(0, 0, 0, 0)')


def test_menu_do_quadro_tem_a_fonte_e_o_recuo_do_dropdown_do_5(logado) -> None:
    page = logado('admin')
    page.goto(INICIO)
    page.locator('.portlet-header [data-bs-toggle="menu"]').first.click()
    menu = page.locator('.portlet-header .menu.show').first
    expect(menu).to_be_visible()

    item = menu.locator('.menu-item').first
    expect(menu).to_have_css('font-size', '13px')
    expect(item).to_have_css('font-size', '13px')
    expect(item).to_have_css('padding', '5px 15px')
    expect(menu).to_have_css('box-shadow', 'none')
    # Item em foco (teclado) ou sob o mouse tem destaque.
    page.keyboard.press('ArrowDown')
    expect(page.locator('.menu.show .menu-item:focus')).not_to_have_css('background-color', 'rgba(0, 0, 0, 0)')


def test_caret_do_botao_do_quadro_como_no_5(logado) -> None:
    page = logado('admin')
    page.goto(INICIO)
    toggle = page.locator('.portlet-header [data-bs-toggle="menu"]').first
    assert toggle.evaluate("e => getComputedStyle(e, '::after').content") not in ('none', 'normal')
    expect(toggle).to_have_css('white-space', 'nowrap')


def test_distintivo_e_mensagem_sem_a_borda_nova_do_6(logado) -> None:
    page = logado('admin')
    _abre_guia(page, 'mensagens')
    expect(page.locator('#mensagens-tab-pane .alert').first).to_have_css('border-top-width', '0px')
    # O texto do alerta segue a cor de ênfase do Bootstrap 5 (o 6 deixou de defini-la).
    expect(page.locator('#mensagens-tab-pane .alert.alert-warning').first).to_have_css('color', 'rgb(102, 77, 3)')

    _abre_guia(page, 'componentes')
    distintivo = page.locator('#componentes-tab-pane .badge').first
    expect(distintivo).to_have_css('border-top-width', '0px')
    expect(distintivo).to_have_css('display', 'inline-flex')


def test_switch_do_suap_nao_ganha_o_visual_do_switch_do_6(logado) -> None:
    page = logado('admin')
    _abre_guia(page, 'formularios')
    chave = page.locator('#formularios-tab-pane label.switch').first

    expect(chave).to_have_css('background-color', 'rgba(0, 0, 0, 0)')
    expect(chave).to_have_css('border-top-width', '0px')
    assert chave.evaluate("e => getComputedStyle(e, '::before').content") == 'none'


def test_raiz_sem_a_faixa_fixa_de_rolagem_do_6(logado) -> None:
    page = logado('admin')
    page.goto(INICIO)

    expect(page.locator('html')).to_have_css('scrollbar-gutter', 'auto')


# --- O que o Bootstrap 6 mudou fora dos componentes: títulos, hr, caption, container, esqueleto e as variáveis dos utilitários ---


def _injeta(page: Page, html: str) -> None:
    page.evaluate("(html) => document.body.insertAdjacentHTML('beforeend', html)", html)


def test_titulos_hr_e_caption_como_no_bootstrap_5(logado) -> None:
    page = logado('admin')
    _abre_guia(page, 'tabelas_e_listas')
    _injeta(page, '<hr id="zz-hr">')

    expect(page.locator('div.title-container h3').first).to_have_css('margin-bottom', '5px')
    expect(page.locator('#zz-hr')).to_have_css('opacity', '0.25')
    legenda = page.locator('#tabelas_e_listas-tab-pane caption').first
    expect(legenda).to_have_css('color', 'rgba(33, 37, 41, 0.75)')
    expect(legenda).to_have_css('text-align', 'left')


def test_container_e_esqueleto_como_no_bootstrap_5(logado) -> None:
    page = logado('admin')
    page.set_viewport_size({'width': 1280, 'height': 800})
    page.goto(INICIO)
    _injeta(page, '<div id="zz-container" class="container"></div><div id="zz-sk" class="placeholder"></div>')

    expect(page.locator('#zz-container')).to_have_css('max-width', '1140px')
    expect(page.locator('#zz-sk')).to_have_css('opacity', '0.5')
    expect(page.locator('#zz-sk')).to_have_css('border-top-left-radius', '0px')


def test_utilitario_de_borda_do_5_segue_a_cor_de_borda_do_tema(logado) -> None:
    """``.border`` lê o ``--bs-border-color`` vivo, que o tema redefine (como no 5); o 6 declara o mesmo nome com outro valor."""
    page = logado('admin')
    page.goto(INICIO)
    _injeta(page, '<div id="zz-b" class="border"></div><input id="zz-bi" type="checkbox" class="form-check-input">')
    token = page.evaluate(
        """() => { const t = document.createElement('i'); t.style.color = getComputedStyle(document.documentElement).getPropertyValue('--bs-border-color');
            document.body.append(t); const c = getComputedStyle(t).color; t.remove(); return c; }"""
    )

    assert token == 'rgb(204, 204, 204)'
    expect(page.locator('#zz-b')).to_have_css('border-top-color', token)
    expect(page.locator('#zz-bi')).to_have_css('border-top-color', token)


# --- Cache, nomes de classe só do 6 e as famílias do 5 que o compat devolve ---

RAIZ = Path(__file__).resolve().parents[2]
# Nomes que só o Bootstrap 6 define (display:grid, fonte menor...); o 5 não tinha e os templates do SUAP não os pretendem.
CLASSES_SO_DO_6 = {'grid', 'text-sm'}


def test_css_do_bootstrap_e_do_compat_carregam_com_versao_na_url(logado) -> None:
    """O nginx serve ``/static`` por 30 dias: sem ``?v=`` no ``@import`` o visitante antigo ficaria com o CSS do 5 ao lado do JS do 6."""
    page = logado('admin')
    respostas: dict[str, int] = {}
    page.on('response', lambda r: respostas.update({r.url: r.status}) if 'bootstrap' in r.url and r.url.split('?')[0].endswith('.css') else None)
    page.goto(INICIO)
    page.wait_for_load_state('networkidle')

    css = {url.split('?')[0].rsplit('/', 1)[-1]: url for url in respostas}
    assert set(css) == {'bootstrap.min.css', 'bootstrap5-compat.min.css'}, respostas
    assert css['bootstrap.min.css'].endswith('?v=6.0.0-alpha.1')
    assert re.search(r'\?v=[0-9a-f]{10}$', css['bootstrap5-compat.min.css'])
    assert set(respostas.values()) == {200}


def test_versao_do_compat_no_pre_scss_e_o_md5_do_arquivo() -> None:
    """Mexeu no compat sem subir o ``?v=`` do ``pre.scss``? Este teste lembra (o gerador imprime o valor)."""
    compat = (RAIZ / 'djtools/static/djtools/css/bootstrap5-compat.min.css').read_bytes()
    pre = (RAIZ / 'djtools/static/djtools/themes/default/pre.scss').read_text(encoding='utf-8')

    assert f'bootstrap5-compat.min.css?v={hashlib.md5(compat).hexdigest()[:10]}' in pre


def test_templates_sem_classe_que_so_o_bootstrap_6_define() -> None:
    arquivos = subprocess.run(['git', 'ls-files', '*.html'], cwd=RAIZ, capture_output=True, text=True, check=True).stdout.split('\n')
    achados = []
    for arquivo in filter(None, arquivos):
        if arquivo.startswith(('docs/', 'tests/')) or not (RAIZ / arquivo).is_file():
            continue
        texto = (RAIZ / arquivo).read_text(encoding='utf-8', errors='ignore')
        for valor in re.findall(r'class="([^"{}]*)"', texto):
            if CLASSES_SO_DO_6 & set(valor.split()):
                achados.append(f'{arquivo}: class="{valor}"')

    assert not achados, achados


def test_form_group_continua_bloco_sem_o_grid_do_6(logado) -> None:
    page = logado('admin')
    page.goto(INICIO)
    _injeta(page, '<div id="zz-fg" class="form-group"><label id="zz-fgl">Rótulo</label><input id="zz-fgi" type="text"></div>')

    grupo = page.locator('#zz-fg')
    expect(grupo).to_have_css('display', 'block')
    expect(grupo).to_have_css('row-gap', 'normal')


def test_botao_btn_primary_tem_o_visual_e_o_hover_do_5(logado) -> None:
    page = logado('admin')
    page.goto(INICIO)
    # Fixo no alto e na frente: no fim do corpo o botão ficaria sob o rodapé/menu e o hover esbarraria neles.
    _injeta(
        page, '<div style="position:fixed;top:0;left:0;z-index:99999"><button id="zz-bp" type="button" class="btn btn-primary">Salvar</button></div>'
    )
    botao = page.locator('#zz-bp')

    expect(botao).to_have_css('background-color', _token(page, '--btn-color'))  # o `%btn` do tema vence o do Bootstrap
    expect(botao).to_have_css('border-top-width', '0px')
    assert botao.evaluate("e => getComputedStyle(e).getPropertyValue('--bs-btn-bg')") == '#0d6efd'  # a família do 5 chegou
    botao.hover()
    expect(botao).to_have_css('background-color', _token(page, '--btn-active-color'))  # o hover do botão do tema, como no 5


def test_tabela_e_cabecalho_coloridos_do_5_pintam_o_texto_e_a_borda(logado) -> None:
    page = logado('admin')
    page.goto(INICIO)
    _injeta(
        page,
        '<table id="zz-ti" class="table-info"><tbody><tr><td>a</td></tr></tbody></table>'
        '<table class="table table-sm"><thead id="zz-tl" class="table-light"><tr><th>h</th></tr></thead></table>',
    )

    expect(page.locator('#zz-ti')).to_have_css('color', 'rgb(0, 0, 0)')
    expect(page.locator('#zz-ti')).to_have_css('border-top-color', 'rgb(166, 195, 202)')
    expect(page.locator('#zz-tl')).to_have_css('color', 'rgb(0, 0, 0)')


def test_form_check_do_5_desenha_a_caixa_e_marca_de_azul(logado) -> None:
    page = logado('admin')
    page.goto(INICIO)
    _injeta(
        page,
        '<div id="zz-fc" class="form-check"><input id="zz-fci" type="checkbox" class="form-check-input" checked>'
        '<label class="form-check-label" for="zz-fci">Marcar</label></div>',
    )

    expect(page.locator('#zz-fc')).to_have_css('padding-left', '19.5px')
    caixa = page.locator('#zz-fci')
    expect(caixa).to_have_css('appearance', 'none')
    expect(caixa).to_have_css('border-top-width', '1px')
    expect(caixa).to_have_css('background-color', 'rgb(13, 110, 253)')


# --- Faixa de abas como no 5: linha pela borda, aba que a cobre, ativa pintada pelas variáveis, switch no fluxo ---


def test_faixa_de_abas_tem_a_borda_do_5_e_nao_a_sombra_do_6(logado) -> None:
    page = logado('admin')
    _abre_detalhe(page)

    faixa = page.locator('ul.nav.nav-tabs').first
    expect(faixa).to_have_css('box-shadow', 'none')
    expect(faixa).to_have_css('border-bottom-width', '1px')
    expect(faixa).to_have_css('border-bottom-style', 'solid')
    # Toda aba se estica até a linha (o `flex` do 6 no `.nav-item`): com uma aba mais alta (rótulo em duas linhas, badge), a ativa
    # ainda cobre a linha
    fundos = faixa.evaluate(
        """u => {
            const abas = [...u.querySelectorAll('.nav-link')].filter(e => e.offsetParent);
            abas.filter(e => !e.classList.contains('active')).at(-1).insertAdjacentHTML('beforeend', '<br>segunda linha');
            return [u, ...abas].map(e => e.getBoundingClientRect().bottom);
        }"""
    )
    assert len(set(fundos)) == 1, fundos


def test_aba_cobre_a_linha_tem_raio_do_5_e_quebra_linha_como_texto(logado) -> None:
    page = logado('admin')
    _abre_detalhe(page)
    aba = page.locator(ABAS).first

    expect(aba).to_have_css('margin-bottom', '-1px')
    expect(aba).to_have_css('border-top-left-radius', '3.75px')
    expect(aba).to_have_css('border-bottom-left-radius', '0px')
    expect(aba).to_have_css('white-space', 'normal')
    expect(aba).to_have_css('row-gap', 'normal')


def test_aba_ativa_usa_cor_e_fundo_das_variaveis_do_tema(logado) -> None:
    """No 5 a regra ``.nav-link.active`` do Bootstrap pintava a ativa; no 6 ela fica em camada e o ``.nav-link`` do tema a vencia."""
    page = logado('admin')
    _abre_detalhe(page)
    ativa = page.locator('.nav-tabs .nav-link.active').first
    esperado = ativa.evaluate(
        """e => { const s = getComputedStyle(e.closest('.nav-tabs'));
            const t = document.createElement('i'); document.body.append(t);
            const cor = v => { t.style.color = s.getPropertyValue(v); return getComputedStyle(t).color; };
            const r = [cor('--bs-nav-tabs-link-active-color'), cor('--bs-nav-tabs-link-active-bg')]; t.remove(); return r; }"""
    )

    expect(ativa).to_have_css('color', esperado[0])
    expect(ativa).to_have_css('background-color', esperado[1])


def test_switch_fica_sem_margem_propria_e_com_o_input_no_fluxo(logado) -> None:
    page = logado('admin')
    page.goto(INICIO)
    _injeta(page, '<label id="zz-sw" class="switch"><input id="zz-swi" type="checkbox"><span class="slider"></span></label>')

    expect(page.locator('#zz-sw')).to_have_css('margin-bottom', '0px')
    expect(page.locator('#zz-swi')).to_have_css('position', 'static')
    expect(page.locator('#zz-swi')).to_have_css('appearance', 'auto')


def test_tabela_base_do_5_da_o_recuo_e_o_fundo_da_celula(logado) -> None:
    """``<table class="table">``: o 6 define outra tabela (em camada); o compat devolve a do 5 (célula de .5rem e fundo ``--bs-table-bg``)."""
    page = logado('admin')
    page.goto(INICIO)
    _injeta(
        page,
        '<table class="table table-striped"><tbody><tr><td id="zz-t1">a</td></tr><tr><td id="zz-t2">b</td></tr></tbody></table>'
        '<table class="table table-sm"><tbody><tr><td id="zz-ts">c</td></tr></tbody></table>',
    )

    expect(page.locator('#zz-t1')).to_have_css('padding-top', '5px')
    expect(page.locator('#zz-t1')).to_have_css('background-color', 'rgb(255, 255, 255)')
    expect(page.locator('#zz-ts')).to_have_css('padding-top', '2.5px')
    expect(page.locator('#zz-t1')).to_have_css('box-shadow', re.compile(r'rgba\(0, 0, 0, 0\.05\) 0px 0px 0px 9999px inset'))  # a listra da 1ª linha
