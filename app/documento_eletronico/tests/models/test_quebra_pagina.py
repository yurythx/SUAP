from django.template.loader import render_to_string

from djtools.templatetags.filters.sanitize import sanitize
from suap.settings_base import TINYMCE_DEFAULT_CONFIG


MARCADOR_QUEBRA_PAGINA = '<div class="page-break"></div>'
REGRA_QUEBRA_PAGINA = '.page-break { display: block; page-break-after: always; break-after: page; }'


def test_tinymce_persiste_quebra_de_pagina_como_elemento_html() -> None:
    assert TINYMCE_DEFAULT_CONFIG['pagebreak_separator'] == MARCADOR_QUEBRA_PAGINA


def test_marcador_de_quebra_de_pagina_sobrevive_a_sanitizacao() -> None:
    html = sanitize(MARCADOR_QUEBRA_PAGINA, 'processo_eletronico')

    assert MARCADOR_QUEBRA_PAGINA in html


def test_marcador_legado_e_convertido_apenas_na_renderizacao() -> None:
    html = sanitize('<p>Antes</p><!-- pagebreak --><p>Depois</p>', 'processo_eletronico')

    assert MARCADOR_QUEBRA_PAGINA in html
    assert '<!-- pagebreak -->' not in html


def test_marcador_provoca_quebra_na_visualizacao_e_impressao() -> None:
    css = render_to_string('includes/tabela_impressao_css_include.html')

    assert REGRA_QUEBRA_PAGINA in css
