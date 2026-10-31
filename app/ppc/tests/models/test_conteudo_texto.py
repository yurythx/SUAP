from ppc.models import Conteudo


def test_preview_substitui_marcadores_sem_executar_tags() -> None:
    conteudo = Conteudo(texto='<p>{{ nome_curso }}</p>{% include "nope.html" %}')

    assert conteudo.get_texto_preview() == '<p>[NOME DO CURSO]</p>{% include "nope.html" %}'
