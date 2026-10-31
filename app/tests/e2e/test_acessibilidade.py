"""Gate de acessibilidade do esqueleto: axe-core nas telas que todo módulo herda.

Por que estas telas: cada uma exercita uma camada compartilhada — início (``base.html``, menu,
rodapé), formulário com erro (``render_form``/``render_field``), listagem do admin
(changelist) e detalhe de objeto. Falha com violação ``serious``/``critical``; a mensagem
lista regra e seletor. Spec: ``docs/superpowers/specs/2026-10-14-acessibilidade-esqueleto-design.md``.
"""

import re
from collections.abc import Callable

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import Page, expect
from pytest_django.live_server_helper import LiveServer

from tests.e2e.test_tema_visual import _token

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

SERVIDOR_SEM_GRUPO = '7000001'  # criado pelo `e2e_seed` de `tests/e2e/conftest.py`
IMPACTOS_BLOQUEANTES = {'serious', 'critical'}

# Regra axe -> motivo. Só entra o que está FORA do esqueleto (spec, "Fora do escopo"), com motivo.
REGRAS_DISPENSADAS: dict[str, str] = {}

# (regra, seletor do axe) -> motivo. Dispensa um nó só, sem cegar a regra no esqueleto das outras telas.
NOS_DISPENSADOS: dict[tuple[str, str], str] = {
    ('aria-prohibited-attr', "['dt > .fa-question-circle.fas']"): (
        'rh/templates/servidor.html: aria-label em <span> sem role no ícone do e-mail Google Sala de Aula (template de módulo)'
    ),
}


def _violacoes(page: Page) -> list[str]:
    # ``settings_test`` usa DEBUG=True e ``body.debug`` pinta sidebar e rodapé com ``--debug-color``:
    # sem isto o contraste seria medido contra um fundo que não existe em produção. O ``reduce`` antes zera
    # as transições do tema (``aside`` tem ``transition: all``), senão o axe mediria o fundo a meio caminho.
    page.emulate_media(reduced_motion='reduce')
    page.evaluate("document.body.classList.remove('debug')")
    # Mesmo com transição de 0,01 ms, o estilo novo só vale no frame seguinte.
    page.evaluate('() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))')
    resultado = Axe().run(page)
    violacoes = []
    for v in resultado.response['violations']:
        if v['impact'] not in IMPACTOS_BLOQUEANTES or v['id'] in REGRAS_DISPENSADAS:
            continue
        alvos = [str(no['target']) for no in v['nodes'] if (v['id'], str(no['target'])) not in NOS_DISPENSADOS]
        if alvos:
            violacoes.append(f'{v["id"]} ({v["impact"]}): ' + ', '.join(alvos))
    return violacoes


def _abrir(page: Page, url: str) -> None:
    """``goto`` que falha em 404/500: axe numa página de erro daria um verde falso."""
    resposta = page.goto(url)
    assert resposta is not None, url
    assert resposta.ok, f'{url} respondeu {resposta.status}'


def _inicio(page: Page) -> None:
    _abrir(page, '/')


def _formulario_com_erro(page: Page) -> None:
    _abrir(page, '/djtools/give_permission/')
    page.click('input[name=atribuirpermissao_form]')
    expect(page.locator('.errorlist').first).to_be_visible()  # audita o form com erro, não o limpo


def _listagem_admin(page: Page) -> None:
    _abrir(page, '/admin/rh/pessoajuridica/')


def _detalhe(page: Page) -> None:
    # Servidor semeado pelo conftest (matrícula numérica): o `admin` não tem URL de detalhe (`<int:...>`).
    _abrir(page, f'/rh/servidor/{SERVIDOR_SEM_GRUPO}/')


TELAS: dict[str, Callable[[Page], None]] = {
    'inicio': _inicio,
    'formulario_com_erro': _formulario_com_erro,
    'listagem_admin': _listagem_admin,
    'detalhe': _detalhe,
}


@pytest.mark.parametrize('tela', TELAS)
def test_tela_sem_violacao_seria(logado, tela: str) -> None:
    page = logado('admin')
    TELAS[tela](page)
    page.wait_for_load_state('networkidle')
    assert _violacoes(page) == []


TEMAS = ['padrao', 'modo-daltonismo', 'alto-contraste', 'aurora', 'dunas', 'govbr', 'ifs', 'luna']
# Variantes de botão, status, badge e etapas, injetadas na página inicial para medir cada uma em cada tema.
AMOSTRAS = (
    '<div id="amostras-contraste">'
    '<ul class="action-bar"><li><a class="btn success" href="#">Adicionar</a></li><li><a class="btn primary" href="#">Editar</a></li>'
    '<li><a class="btn danger" href="#">Remover</a></li><li><a class="btn warning" href="#">Atenção</a></li>'
    '<li><a class="btn default" href="#">Padrão</a></li><li><a class="btn" href="#">Simples</a></li></ul>'
    '<p><a class="btn success" href="#">s</a> <a class="btn primary" href="#">p</a> <a class="btn danger" href="#">d</a> '
    '<a class="btn warning" href="#">w</a> <a class="btn default" href="#">df</a></p>'
    '<p><span class="status status-success">Sucesso</span> <span class="status status-error">Erro</span> '
    '<span class="status status-info">Info</span> <span class="status status-alert">Alerta</span> '
    '<span class="status status-default">Padrão</span> <span class="status status-final">Final</span></p>'
    '<p><span class="badge">3</span></p>'
    '<ul class="steps"><li><span class="step-success active">Feito</span></li><li><span class="step-info active">Info</span></li>'
    '<li><span class="step-alert active">Andamento</span></li><li><span class="step-danger active">Erro</span></li></ul>'
    '</div>'
)
MARCA_PAGINA_ATUAL = """() => {
  const item = document.querySelector('._main_menu li[id^="menu-item-"]:not(.has-child)');
  open_menu_item(item.id.replace('menu-item-', ''));
}"""
# Placeholder abaixo de 4,5:1: o axe não mede placeholder.
PLACEHOLDERS_BAIXOS = """() => {
  const lum = c => c.match(/[\\d.]+/g).slice(0, 3).map(Number).map(v => (v /= 255) <= .03928 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4)
    .reduce((s, v, i) => s + v * [.2126, .7152, .0722][i], 0);
  const fundo = e => { for (; e; e = e.parentElement) { const c = getComputedStyle(e).backgroundColor; if (!/rgba\\(0, 0, 0, 0\\)/.test(c)) return c; } return 'rgb(255, 255, 255)'; };
  return [...document.querySelectorAll('input[placeholder], textarea[placeholder]')].filter(e => e.placeholder && e.offsetParent).flatMap(e => {
    const [a, b] = [lum(getComputedStyle(e, '::placeholder').color), lum(fundo(e))];
    const razao = (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
    return razao < 4.5 ? [`placeholder de ${e.id || e.name}: ${razao.toFixed(2)}:1`] : [];
  });
}"""


def _contraste(page: Page, tema: str) -> list[str]:
    page.emulate_media(reduced_motion='reduce')
    # O rodapé de DEBUG (``#debug``) só existe em desenvolvimento.
    page.evaluate("document.body.classList.remove('debug'); document.getElementById('debug')?.remove()")
    page.evaluate('() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))')
    # Transição que o tema não encurta com movimento reduzido (o fundo de debug do Aurora): espera terminar.
    page.evaluate('() => Promise.allSettled(document.getAnimations().filter(a => a instanceof CSSTransition).map(a => a.finished))')
    falhas = page.evaluate(PLACEHOLDERS_BAIXOS)
    for v in Axe().run(page, options={'runOnly': ['color-contrast']}).response['violations']:
        for no in v['nodes']:
            # Ícones do rodapé do Dunas (3,1:1): glifo, vale o 1.4.11 (3:1); o axe o mede como texto.
            if tema == 'dunas' and 'class="icone fas' in no['html']:
                continue
            falhas.append(f'{no["target"]} {no["html"][:80]}')
    return falhas


@pytest.mark.parametrize('tema', TEMAS)
def test_contraste_nos_temas(logado, tema: str) -> None:
    """Contraste de texto (4,5:1) nas telas do esqueleto e nas variantes de componente, em cada tema (fase 4)."""
    page = logado('admin')
    _abrir(page, f'/comum/alterar_tema/?theme={tema}')
    try:
        falhas = {}
        for tela, abrir in TELAS.items():
            abrir(page)
            page.wait_for_load_state('networkidle')
            if tela == 'inicio':
                page.evaluate("(html) => document.querySelector('main').insertAdjacentHTML('afterbegin', html)", AMOSTRAS)
            # Marca uma página atual no menu (o item fica marcado só quando a sessão lembra o último item aberto).
            page.evaluate(MARCA_PAGINA_ATUAL)
            expect(page.locator('._main_menu [aria-current="page"]').first).to_be_attached()
            falhas[tela] = _contraste(page, tema)
        assert {tela: f for tela, f in falhas.items() if f} == {}
    finally:
        # O tema vai para a preferência do admin, que os outros testes compartilham.
        page.request.get('/comum/alterar_tema/?theme=padrao')


def test_foco_por_teclado_e_visivel_e_clique_nao(logado) -> None:
    page = logado('admin')
    # Não a página inicial: lá ``index.html`` põe ``autofocus`` na busca do menu e o 1º Tab já sai dela.
    _abrir(page, '/djtools/give_permission/')
    page.keyboard.press('Tab')
    atalho = page.locator('#accesskeys a').first
    expect(atalho).to_be_focused()
    expect(atalho).to_have_css('outline-width', '2px')  # espera a transição do tema
    assert atalho.bounding_box()['x'] >= 0  # o skip link aparece na tela

    # Clique de mouse não mostra anel. Sonda ``<a>``: num ``<button>`` o reboot do Bootstrap
    # (``button:focus:not(:focus-visible)``) zera o outline sozinho e a asserção não provaria nada.
    page.evaluate(
        """() => {
            const a = document.createElement('a');
            a.id = 'sonda-foco';
            a.href = 'javascript:void(0)';
            a.textContent = 'sonda';
            document.querySelector('main').appendChild(a);
        }"""
    )
    sonda = page.locator('#sonda-foco')
    sonda.click()
    expect(sonda).to_be_focused()
    expect(sonda).to_have_css('outline-style', 'none')


def test_botao_com_foco_por_teclado_mostra_anel(logado) -> None:
    page = logado('admin')
    _abrir(page, '/djtools/give_permission/')
    botao = page.locator('#topodapagina')  # ``.btn`` sem variante, presente em toda tela do esqueleto
    botao.focus()
    page.keyboard.press('Shift+Tab')
    page.keyboard.press('Tab')  # volta ao botão com modalidade de teclado
    expect(botao).to_be_focused()
    expect(botao).to_have_css('outline-width', '2px')


def test_toggle_da_sidebar_anuncia_estado(logado) -> None:
    page = logado('admin')
    page.set_viewport_size({'width': 1280, 'height': 900})
    _abrir(page, '/')
    botao = page.locator('#toggleSidebar')
    expect(botao).to_have_attribute('aria-expanded', 'true')
    try:
        with page.expect_response('**/comum/retrair_menu/'):
            botao.click()
        expect(botao).to_have_attribute('aria-expanded', 'false')
        with page.expect_response('**/comum/expandir_menu/'):
            botao.click()
        expect(botao).to_have_attribute('aria-expanded', 'true')
    finally:
        # O estado vai para a sessão do admin, que os outros testes compartilham: restaura mesmo se falhar no meio.
        page.request.get('/comum/expandir_menu/')


def test_tela_estreita_recolhe_a_sidebar(logado) -> None:
    page = logado('admin')
    page.set_viewport_size({'width': 375, 'height': 800})
    _abrir(page, '/')
    expect(page.locator('body')).to_have_class(re.compile(r'\bhideSidebar\b'))
    expect(page.locator('#mobilemenu .toggleSidebar')).to_have_attribute('aria-expanded', 'false')


def test_login_sem_violacao_seria(page: Page, live_server: LiveServer) -> None:
    """A tela de login (anônima, ``base_anonima``) limpa e com erro de credencial."""
    resposta = page.goto(live_server.url + '/accounts/login/')
    assert resposta is not None
    assert resposta.ok
    page.wait_for_load_state('networkidle')
    assert _violacoes(page) == []

    page.fill('#id_username', 'naoexiste')
    page.fill('#id_password', 'errada')
    page.click('input[type=submit]')
    page.wait_for_load_state('networkidle')
    assert _violacoes(page) == []


def test_login_sem_animacao_em_loop_infinito(page: Page, live_server: LiveServer) -> None:
    """WCAG 2.2.2: a ilustração flutua 5 vezes e o brilho do fundo vai e volta uma vez; depois param."""
    page.emulate_media(reduced_motion='no-preference')
    page.goto(live_server.url + '/accounts/login/')
    voltas = """() => Object.fromEntries(document.getAnimations().map(a => [a.animationName, a.effect.getTiming().iterations]))"""
    animacoes = page.evaluate(voltas)
    assert animacoes['login-flutuar'] == 5
    assert animacoes['login-brilho'] == 2
    assert float('inf') not in animacoes.values()

    # O rótulo do campo em foco muda de cor só com animação ligada: tem de manter o contraste (4,5:1) sobre o cartão branco.
    page.focus('#id_username')
    expect(page.locator('label[for=id_username]')).to_have_css('color', _token(page, '--primary-750'))
