from django.template import Library

from ponto.models import AbonoChefia

register = Library()


@register.simple_tag
def get_descricoes_abonos(acao_abono):
    descricoes_abonos = AbonoChefia.DESCRICOES_ABONO
    return descricoes_abonos.get(acao_abono, '')
