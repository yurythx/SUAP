# No seu aplicativo, crie um arquivo chamado custom_filters.py

from django import template

register = template.Library()


@register.simple_tag
def get_qtd_disciplinas_por_periodo(matrizppc, periodo, semestre=None):
    return matrizppc.get_qtd_disciplinas_por_periodo(periodo, semestre)


@register.simple_tag
def get_total_creditos_por_planos_disciplinappc(matrizppc, nucleo_id, periodo, semestre=None):
    if nucleo_id == 0:
        nucleo_id = None
    return matrizppc.get_total_creditos_por_planos_disciplinappc(nucleo_id, periodo, semestre)
