from documento_eletronico.utils import processar_template_ckeditor


def test_substitui_variaveis_e_variantes_de_caixa() -> None:
    texto = '<p>{{ setor_nome }} | {{setor_nome_maiusculo}} | {{ setor_nome_minusculo }} | {{ setor_nome_iniciais_maiusculas }}</p>'

    html = processar_template_ckeditor(texto, {'setor_nome': 'Diretoria de <b>Gestão</b>'})

    assert html == '<p>Diretoria de <b>Gestão</b> | DIRETORIA DE <B>GESTÃO</B> | diretoria de <b>gestão</b> | Diretoria De <B>Gestão</B></p>'


def test_variavel_desconhecida_vira_vazio() -> None:
    assert processar_template_ckeditor('a{{ inexistente }}b', None) == 'ab'


def test_tags_de_template_nao_sao_executadas() -> None:
    # #17926: o corpo vinha do editor e era renderizado pelo engine do Django (Sentry SUAP-WZ8: `{% include "nope.html" %}`).
    texto = '{% include "nope.html" %}{% load static %}{% debug %}{# comentario #}{{ 23421.000487.2020 }}'

    assert processar_template_ckeditor(texto, {'setor_nome': 'X'}) == texto


def test_filtro_upper_escapa_como_o_django() -> None:
    assert processar_template_ckeditor('{{ setor_nome|upper }}', {'setor_nome': 'Diretoria <b>X</b>'}) == 'DIRETORIA &lt;B&gt;X&lt;/B&gt;'
