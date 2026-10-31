"""Tokens visuais da fase 1 da modernização, numa tela real (tema Padrão).

Trava os ajustes que a spec ``docs/superpowers/specs/2026-10-15-modernizacao-fase1-tokens-design.md`` decidiu
e que dá para medir numa tela real: texto base 13px (pelo token), título da página em grafite, cabeçalho de caixa aberta
branco com divisória e anel de foco por teclado, cabeçalho de tabela em caixa normal, realce da linha sob o mouse
a precedência da cor de estado (linha selecionada) sobre esse realce e a fonte Open Sans hospedada no SUAP,
com números tabulares nas tabelas. A sombra discreta não é testada aqui.
"""

import pytest
from playwright.sync_api import expect

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

LISTAGEM = '/admin/rh/pessoajuridica/'
CAIXA = '/comum/acessibilidade/'  # tem {% box %} aberto, sem dado dependente de seed


def _token(page, nome: str) -> str:
    """Valor computado de um token de cor do :root, normalizado como cor computada num elemento sonda."""
    return page.evaluate(
        """nome => {
            if (!getComputedStyle(document.documentElement).getPropertyValue(nome).trim()) throw new Error(`token ${nome} inexistente ou vazio`);
            const s = document.createElement('span'); s.style.color = `var(${nome})`; document.body.append(s);
            const v = getComputedStyle(s).color; s.remove(); return v;
        }""",
        nome,
    )


def test_listagem_usa_os_tokens_visuais(logado) -> None:
    page = logado('admin')
    page.goto(LISTAGEM)

    expect(page.locator('body')).to_have_css('font-size', '13px')
    expect(page.locator('.title-container h2')).to_have_css('color', _token(page, '--grey-850'))


def test_fonte_open_sans_hospedada_carrega_e_tabela_usa_numeros_tabulares(logado) -> None:
    """A Open Sans vem de /static (sem Google Fonts) e de fato carrega; um caminho errado cairia no fallback do sistema."""
    page = logado('admin')
    page.goto(LISTAGEM)

    familia = page.locator('body').evaluate('e => getComputedStyle(e).fontFamily')
    assert familia.startswith('"Open Sans"'), familia
    assert page.evaluate(
        'async () => { await document.fonts.ready; return document.fonts.check(\'13px "Open Sans"\') && [...document.fonts].some(f => f.family.replace(/"/g, "") === "Open Sans" && f.status === "loaded"); }'
    )
    assert not page.evaluate('() => [...document.styleSheets].some(s => (s.href || "").includes("fonts.googleapis"))')
    expect(page.locator('#result_list').first).to_have_css('font-variant-numeric', 'tabular-nums')


def test_cabecalho_de_caixa_aberta_e_branco_com_divisoria(logado) -> None:
    page = logado('admin')
    page.goto(CAIXA)
    cabecalho = page.locator('.accordion-button:not(.collapsed)').first

    expect(cabecalho).to_have_css('background-color', _token(page, '--white'))
    expect(cabecalho).to_have_css('box-shadow', f'{_token(page, "--grey-150")} 0px -1px 0px 0px inset')


def test_cabecalho_de_caixa_aberta_mantem_o_anel_de_foco_por_teclado(logado) -> None:
    page = logado('admin')
    page.goto(CAIXA)
    cabecalho = page.locator('.accordion-button:not(.collapsed)').first

    cabecalho.focus()
    page.keyboard.press('Shift+Tab')
    page.keyboard.press('Tab')  # modalidade teclado, foco de volta no cabeçalho
    expect(cabecalho).to_be_focused()

    # Bootstrap 6: o anel é o outline global do :focus-visible; a divisória do cabeçalho aberto continua
    expect(cabecalho).to_have_css('outline-style', 'solid')
    expect(cabecalho).to_have_css('outline-color', _token(page, '--primary-700'))
    expect(cabecalho).to_have_css('box-shadow', f'{_token(page, "--grey-150")} 0px -1px 0px 0px inset')


def test_tabela_tem_cabecalho_em_caixa_normal_e_realce_da_linha(logado) -> None:
    page = logado('admin')
    page.goto(LISTAGEM)
    expect(page.locator('#result_list tbody tr').first).to_be_visible()  # o seed cria uma PJ

    expect(page.locator('#result_list thead th').last).to_have_css('text-transform', 'none')  # a caixa alta da fase 1 saiu a pedido
    celula = page.locator('#result_list tbody tr').first.locator('td').last
    celula.hover()
    expect(celula).to_have_css('background-color', _token(page, '--primary-50'))


def test_linha_selecionada_mantem_a_cor_de_estado_sob_o_mouse(logado) -> None:
    page = logado('admin')
    page.goto(LISTAGEM)
    linha = page.locator('#result_list tbody tr').first
    expect(linha).to_be_visible()

    # A changelist de PJ não tem ação em lote (o SUAP remove a delete_selected), logo nenhum checkbox: marca a linha
    # como o JS do admin marcaria. A regra sob teste é o CSS de `tr.selected`, não quem põe a classe.
    linha.evaluate("el => el.classList.add('selected')")
    estado, realce = _token(page, '--table-highlight-bg-color'), _token(page, '--table-row-hover-color')
    assert estado != realce  # senão o teste não distingue quem venceu
    celula = linha.locator('td').last
    expect(celula).to_have_css('background-color', estado)

    celula.hover()
    expect(celula).to_have_css('background-color', estado)
