"""Comparação de versões do admin (``reversion-compare/compare_partial.html``)."""

from types import SimpleNamespace

from diff_match_patch import diff_match_patch
from django.template.loader import render_to_string


def test_diff_com_html_injetado_sai_sanitizado() -> None:
    motor = diff_match_patch()
    diff = motor.diff_prettyHtml(motor.diff_main('<p>Assunto</p>', '<p>Assunto</p><img src="x" onerror="alert(`xss-no-diff`)">'))
    campo = SimpleNamespace(field=SimpleNamespace(verbose_name='Assunto', help_text=''), diff=diff, is_related=False, follow=False)

    html = render_to_string('documento_eletronico/reversion-compare/compare_partial.html', {'compare_data': [campo]})

    assert '<p>Assunto</p>' in html
    assert 'xss-no-diff' not in html
