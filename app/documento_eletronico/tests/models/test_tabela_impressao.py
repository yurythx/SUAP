from django.template.loader import render_to_string

from djtools.templatetags.filters.sanitize import sanitize
from suap.settings_base import TINYMCE_DEFAULT_CONFIG


REGRA_BORDA_ZERO = (
    'table:not([border]), table:not([border]) td, table:not([border]) th, '
    'table[border=""], table[border=""] td, table[border=""] th, '
    'table[border="0"], table[border="0"] td, table[border="0"] th { border-width: 0; }'
)


def test_atributo_border_do_tinymce_exibe_bordas_na_impressao() -> None:
    css = ' '.join(render_to_string('includes/tabela_impressao_css_include.html').split())

    assert REGRA_BORDA_ZERO in css
    assert 'table[border="1"]' not in css


def test_atributo_border_do_tinymce_exibe_bordas_no_editor() -> None:
    css = TINYMCE_DEFAULT_CONFIG['content_style']

    assert REGRA_BORDA_ZERO in css
    assert 'table[border="1"]' not in css


def test_linha_de_tabela_nao_quebra_entre_paginas() -> None:
    css = render_to_string('includes/tabela_impressao_css_include.html')

    assert 'table tr { page-break-inside: avoid; break-inside: avoid; }' in css


def test_altura_da_tabela_se_adapta_ao_conteudo_na_impressao() -> None:
    css = render_to_string('includes/tabela_impressao_css_include.html')

    assert 'table, table tr, table td, table th { height: auto !important; }' in css


def test_css_nao_desativa_repeticao_de_cabecalho_legitimo() -> None:
    css = render_to_string('includes/tabela_impressao_css_include.html')

    assert 'table thead { display: table-row-group; }' not in css


def test_tabela_sem_tbody_e_corrigida_na_renderizacao() -> None:
    html = sanitize('<table><thead><tr><th>Título</th></tr><tr><td>Valor</td></tr></thead></table>', 'processo_eletronico')

    assert '<thead>' not in html
    assert '<tbody>' in html


def test_tabela_com_cabecalho_legitimo_preserva_thead() -> None:
    conteudo = '<table><thead><tr><th>Título</th></tr></thead><tbody><tr><td>Valor</td></tr></tbody></table>'

    html = sanitize(conteudo, 'processo_eletronico')

    assert '<thead>' in html
    assert '<tbody>' in html


def test_tabela_somente_com_cabecalho_preserva_thead() -> None:
    conteudo = '<table><thead><tr><th>Título</th></tr></thead></table>'

    html = sanitize(conteudo, 'processo_eletronico')

    assert '<thead>' in html
    assert '<tbody>' not in html
