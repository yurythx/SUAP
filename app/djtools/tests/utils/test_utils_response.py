from decimal import Decimal

from django.template import Context, Template
from django.utils.safestring import mark_safe

from djtools.utils.response import substituir_marcadores


def test_marcadores_saem_como_o_django_renderizaria() -> None:
    texto = '<p>{{ nome }} | {{quadro}} | {{ ch }} | {{ media }} | {{ vazio }} | {{ inexistente }} | {{ 1200 }}</p>'
    valores = {'nome': "Curso <b>A</b> & 'B'", 'quadro': mark_safe('<table></table>'), 'ch': 1200, 'media': Decimal('7.5'), 'vazio': None}

    assert substituir_marcadores(texto, valores) == Template(texto).render(Context(valores))


def test_tags_de_template_nao_sao_executadas() -> None:
    # #17926: texto do editor renderizado pelo engine do Django executava `{% include %}`, `{% load %}`...
    texto = '{% include "nope.html" %}{% load static %}{% debug %}{# comentario #}{{ Instrumento Musical }}'

    assert substituir_marcadores(texto, {'nome': 'X'}) == texto
