"""Componentes da fase 2 da modernização, numa tela real (tema Padrão).

Spec: ``docs/superpowers/specs/2026-10-15-modernizacao-fase2-componentes-design.md``.
"""

import pytest
from playwright.sync_api import expect

from tests.e2e.test_tema_visual import _token

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

FORMULARIO = '/djtools/give_permission/'
DETALHE = '/rh/servidor/7000001/'
CAIXA = '/comum/acessibilidade/'
GUIA = '/comum/design_system/?tab={}'
# select2 de escolha única já focado (o JS do select2 põe `select2-container--focus`); o formulário só tem select2 múltiplo.
SELECT2_SIMPLES = (
    '<span class="select2 select2-container select2-container--default select2-container--focus">'
    '<span class="selection"><span id="select2-simples" class="select2-selection select2-selection--single" tabindex="0">'
    '<span class="select2-selection__rendered">Valor</span></span></span></span>'
)


def _injeta(page, html: str) -> None:
    page.evaluate("(html) => document.querySelector('main, #content, body').insertAdjacentHTML('beforeend', html)", html)


def _abre_guia(page, aba: str) -> None:
    """Abre a aba do guia e expande todas as caixas (o conteúdo fica recolhido por padrão)."""
    page.goto(GUIA.format(aba))
    page.evaluate("(aba) => document.querySelectorAll(`#${aba}-tab-pane .accordion-collapse`).forEach(e => e.classList.add('show'))", aba)


def test_botao_padrao_preenchido_escuro_sem_contorno(logado) -> None:
    """O contorno branco da fase 2 saiu a pedido: o `.btn` sem variante volta ao preenchimento escuro de `%btn`."""
    page = logado('admin')
    _abre_guia(page, 'botoes_e_acoes')

    # `.btn` sem variante, fora de barra de ações/filtros (nestes o tema pinta o botão como `.default`).
    padrao = page.locator(
        '#botoes_e_acoes-tab-pane a.btn:not(.success, .primary, .danger, .warning, .default, .disabled, .unchecked, .btn-link)'
    ).first
    expect(padrao).to_have_css('background-color', _token(page, '--btn-color'))
    expect(padrao).to_have_css('color', _token(page, '--btn-text-color'))
    assert padrao.evaluate('e => getComputedStyle(e).boxShadow') == 'none'  # sem o contorno de 1px
    padrao.hover()
    expect(padrao).to_have_css('background-color', _token(page, '--btn-active-color'))
    assert '0px 0px 0px 1px' not in padrao.evaluate('e => getComputedStyle(e).boxShadow')  # o hover do tema tem só a sombra interna difusa


def test_botao_de_variante_nao_ganha_contorno(logado) -> None:
    page = logado('admin')
    _abre_guia(page, 'botoes_e_acoes')
    remocao = page.locator('#botoes_e_acoes-tab-pane .btn.danger').first

    expect(remocao).to_have_css('background-color', _token(page, '--danger'))
    assert remocao.evaluate('e => getComputedStyle(e).boxShadow') == 'none'
    remocao.hover()
    assert _token(page, '--grey-600') not in remocao.evaluate('e => getComputedStyle(e).boxShadow')


def test_campo_preenchido_fica_branco_no_foco_e_vermelho_claro_no_erro(logado) -> None:
    page = logado('admin')
    page.goto(FORMULARIO)
    page.click('input[name=atribuirpermissao_form]')  # submete vazio: "usuarios" é obrigatório (como em test_formulario.py)
    expect(page.locator('.form-row.errors').first).to_be_visible()

    campo_erro = page.locator('.form-row.errors textarea').first
    expect(campo_erro).to_have_css('background-color', _token(page, '--danger-50'))
    expect(campo_erro).to_have_css('border-top-left-radius', '8px')
    icone = page.locator('.form-row .errorlist li').first.evaluate("e => getComputedStyle(e, '::before').content")
    assert icone not in ('none', 'normal', '""'), icone

    selecao = page.locator('.select2-selection').first  # campo de múltipla escolha (select2)
    expect(selecao).to_have_css('background-color', _token(page, '--grey-50'))
    assert page.locator('.select2-search__field').first.evaluate('e => getComputedStyle(e).borderTopStyle') in ('none', 'hidden')

    campo_erro.focus()
    expect(campo_erro).to_have_css('background-color', _token(page, '--white'))
    assert _token(page, '--primary-100') in campo_erro.evaluate('e => getComputedStyle(e).boxShadow')


def test_campo_tem_borda_uniforme_e_placeholder_legivel(logado) -> None:
    page = logado('admin')
    page.goto(FORMULARIO)
    page.evaluate(
        "() => { const i = document.createElement('input'); i.type = 'text'; i.placeholder = 'Digite'; i.id = 'campo-dica'; document.querySelector('main, #content, body').append(i); }"
    )
    # A borda é suave e igual nos quatro lados (a inferior escura, de 3:1, saiu a pedido em 19/10/2026). O select2 segue a mesma regra.
    for campo in (page.locator('#campo-dica'), page.locator('.select2-selection').first):
        for lado in ('top', 'left', 'bottom'):
            expect(campo).to_have_css(f'border-{lado}-color', _token(page, '--grey-150'))

    # No foco a borda inteira passa à cor primária (a inferior não fica cinza).
    page.locator('#campo-dica').focus()
    expect(page.locator('#campo-dica')).to_have_css('border-bottom-color', _token(page, '--primary'))

    # O placeholder do navegador dá 4,49:1 sobre --grey-50; o tema o escurece para passar de 4,5:1.
    cor = page.locator('#campo-dica').evaluate("e => getComputedStyle(e, '::placeholder').color")
    assert cor == _token(page, '--grey-600'), cor


def test_campo_somente_leitura_focado_mantem_o_cinza(logado) -> None:
    page = logado('admin')
    page.goto(FORMULARIO)
    page.evaluate(
        "() => { const i = document.createElement('input'); i.type = 'text'; i.readOnly = true; i.id = 'campo-leitura'; document.querySelector('main, #content, body').append(i); }"
    )
    leitura = page.locator('#campo-leitura')
    expect(leitura).to_have_css('background-color', _token(page, '--grey-400'))
    leitura.focus()
    expect(leitura).to_have_css('background-color', _token(page, '--grey-400'))


def test_fundo_de_erro_so_nos_campos_de_digitacao(logado) -> None:
    page = logado('admin')
    page.goto(FORMULARIO)
    _injeta(
        page,
        '<div class="form-row"><input id="sub-fora" type="submit" value="Enviar"><input id="ro-fora" type="text" readonly></div>'
        '<div class="form-row errors"><input id="sub-erro" type="submit" value="Enviar"><input id="ro-erro" type="text" readonly>'
        '<input id="txt-erro" type="text"></div>',
    )
    # Botão e somente leitura dentro de `.errors` ficam com o fundo que têm fora dele.
    fundo = 'e => getComputedStyle(e).backgroundColor'
    assert page.locator('#sub-erro').evaluate(fundo) == page.locator('#sub-fora').evaluate(fundo)
    assert page.locator('#ro-erro').evaluate(fundo) == page.locator('#ro-fora').evaluate(fundo)
    # O campo de texto continua com o fundo de erro, que cede ao branco no foco.
    expect(page.locator('#txt-erro')).to_have_css('background-color', _token(page, '--danger-50'))
    page.locator('#txt-erro').focus()
    expect(page.locator('#txt-erro')).to_have_css('background-color', _token(page, '--white'))


def test_busca_do_menu_sem_anel_e_com_placeholder_legivel(logado) -> None:
    page = logado('admin')
    page.goto(FORMULARIO)
    busca = page.locator('aside.nav .buscar_menu input[type=search]')
    # O anel claro do campo (%inputs-focus) não entra na barra escura; o placeholder passa de 4,5:1 sobre ela.
    assert busca.evaluate("e => getComputedStyle(e, '::placeholder').color") == _token(page, '--grey-400')
    busca.focus()
    assert busca.evaluate('e => getComputedStyle(e).boxShadow') == 'none'


def test_select2_focado_por_teclado_tem_um_so_indicador(logado) -> None:
    page = logado('admin')
    page.goto(FORMULARIO)
    _injeta(page, '<button id="antes-select2" type="button">x</button>' + SELECT2_SIMPLES)
    page.locator('#antes-select2').focus()
    page.keyboard.press('Tab')
    selecao = page.locator('#select2-simples')
    expect(selecao).to_be_focused()
    # O anel (box-shadow) é o indicador; o outline do :focus-visible global não soma um segundo.
    expect(selecao).to_have_css('outline-style', 'none')
    assert _token(page, '--primary-100') in selecao.evaluate('e => getComputedStyle(e).boxShadow')


def test_mensagem_com_cantos_de_8px(logado) -> None:
    page = logado('admin')
    page.goto(GUIA.format('mensagens'))
    page.evaluate("() => document.querySelector('#mensagens-tab-pane .accordion-collapse').classList.add('show')")
    expect(page.locator('#mensagens-tab-pane .alert').first).to_have_css('border-top-left-radius', '8px')


def test_aba_ativa_de_pasta_e_caixa_com_borda_cinza(logado) -> None:
    """Aba de pasta: a ativa é branca, colada no painel (fundo da borda de baixo) e com faixa de 3px no topo; as inativas
    quase brancas (`--grey-50`), para não parecerem desabilitadas."""
    page = logado('admin')
    page.goto(DETALHE)
    ativa = page.locator('.nav-tabs .nav-link.active').first
    inativa = page.locator('.nav-tabs .nav-link:not(.active)').first
    expect(ativa).to_have_css('background-color', _token(page, '--white'))
    expect(ativa).to_have_css('border-bottom-color', _token(page, '--white'))
    expect(ativa).to_have_css('border-top-color', _token(page, '--grey-300'))
    expect(ativa).to_have_css('box-shadow', f'{_token(page, "--primary-700")} 0px 3px 0px 0px inset')
    expect(inativa).to_have_css('background-color', _token(page, '--grey-50'))
    expect(inativa).to_have_css('border-top-color', _token(page, '--grey-200'))

    ativa.focus()
    page.keyboard.press('Shift+Tab')
    page.keyboard.press('Tab')  # modalidade teclado
    expect(ativa).to_be_focused()
    expect(ativa).to_have_css('outline-style', 'solid')  # o anel global do :focus-visible, além da faixa

    page.goto(CAIXA)
    expect(page.locator('.accordion-item').first).to_have_css('border-top-color', _token(page, '--grey-200'))


def test_aba_ativa_de_pasta_tambem_sob_body_index(logado) -> None:
    page = logado('admin')
    page.goto(DETALHE)
    # Nenhuma das telas body.index (index, painel_controle, monitoramento) tem abas para o admin do seed:
    # injeta a classe para exercitar a regra `body.index .nav-tabs .active`.
    page.evaluate("() => document.body.classList.add('index')")
    ativa = page.locator('.nav-tabs .nav-link.active').first
    expect(ativa).to_have_css('border-bottom-color', _token(page, '--white'))  # colada no painel também sob body.index
    expect(ativa).to_have_css('border-bottom-width', '2px')
