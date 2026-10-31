from django import template
from django.urls import reverse

from acervo_academico.models import ItemRotina

register = template.Library()


@register.filter(name='qtd_itens_simulados')
def qtd_itens_simulados(rotina):
    return rotina.itens.filter(status=ItemRotina.SIMULADO).count()


@register.filter(name='url_itens_por_campus')
def url_itens_por_campus(rotina, campus: int):
    url_changelist = reverse('admin:acervo_academico_itemrotina_changelist')
    return f'{url_changelist}?rotina={rotina.id}&campus={campus}'
