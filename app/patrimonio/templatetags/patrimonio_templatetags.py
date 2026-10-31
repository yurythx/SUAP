from django.db.models import Q
from django.template import Library

from patrimonio.models import ConferenciaSala

register = Library()


@register.filter
def salas_com_observacoes(qs_conferenciaitem):
    ids_conferencias_com_observacao = (
        qs_conferenciaitem.only('conferencia')
        .exclude(Q(conferencia__observacao__isnull=True) | Q(conferencia__observacao=''))
        .values_list('conferencia_id', flat=True)
        .distinct()
    )
    return ConferenciaSala.objects.only('id', 'sala', 'observacao').order_by('sala__nome').filter(pk__in=ids_conferencias_com_observacao).all()
