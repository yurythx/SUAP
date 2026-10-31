from django import template

from plan_v2.models import Acao

register = template.Library()


@register.filter
def status_validacao(situacao):
    status = 'status status-alert'

    if situacao == Acao.SITUACAO_DEFERIDA:
        status = 'status status-success'
    elif situacao == Acao.SITUACAO_INDEFERIDA:
        status = 'status status-error'
    elif situacao == Acao.SITUACAO_ANALISADA:
        status = 'status status-info'

    return status
