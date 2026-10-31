import pytest

from djtools.templatetags.filters.sanitize import sanitize

# O lxml recusa string com declaração XML de encoding (ValueError): é o caso em que a limpeza falha.
HTML_QUE_O_LXML_RECUSA = '<?xml version="1.0" encoding="utf-8"?><p>Ofício</p><img src="x" onerror="alert(1)">'


@pytest.mark.parametrize('skip', ['processo_eletronico', None])
def test_html_que_nao_pode_ser_limpo_sai_escapado(skip: str | None) -> None:
    html = sanitize(HTML_QUE_O_LXML_RECUSA, skip)

    assert '<img' not in html
    assert '&lt;img' in html


@pytest.mark.parametrize('skip', ['processo_eletronico', None])
def test_html_comum_continua_limpo_sem_escapar(skip: str | None) -> None:
    html = sanitize('<p>Ofício</p><img src="x" onerror="alert(1)">', skip)

    assert '<p>Ofício</p>' in html
    assert 'onerror' not in html


@pytest.mark.parametrize('conteudo', ['', None])
def test_conteudo_vazio_vira_texto_vazio(conteudo: str | None) -> None:
    assert sanitize(conteudo, 'processo_eletronico') == ''
