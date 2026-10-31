from django.db.models import Q

from financeiro.models import Evento


def get_eventos_utilizados_notascreditodotacao():
    return Evento.objects.filter(Q(notacreditoitem__isnull=False) | Q(notadotacaoitem__isnull=False)).distinct().order_by('codigo')


def get_eventos_desatualizados_notascredito(unidade_gestora=None):
    """verifica nas notas de crédito se existe algum evento referenciado que não possui tipo (crédito ou débito) definido"""
    if unidade_gestora:
        return (
            Evento.objects.filter(
                Q(notacreditoitem__isnull=False, notacreditoitem__nota_credito__favorecido_ug=unidade_gestora, tipo=None)
                | Q(notacreditoitem__isnull=False, notacreditoitem__nota_credito__emitente_ug=unidade_gestora, tipo=None)
                | Q(notacreditoitem__isnull=False, notacreditoitem__ugr=unidade_gestora, tipo=None)
            )
            .distinct()
            .order_by('codigo')
        )
    else:
        return Evento.objects.filter(notacreditoitem__isnull=False, tipo=None).distinct().order_by('codigo')


def get_eventos_desatualizados_notasdotacao(unidade_gestora=None):
    """verifica nas notas de dotação se existe algum evento referenciado que não possui tipo (crédito ou débito) definido"""
    if unidade_gestora:
        return (
            Evento.objects.filter(
                Q(notadotacaoitem__isnull=False, notadotacaoitem__nota_dotacao__favorecido_ug=unidade_gestora, tipo=None)
                | Q(notadotacaoitem__isnull=False, notadotacaoitem__nota_dotacao__emitente_ug=unidade_gestora, tipo=None)
                | Q(notadotacaoitem__isnull=False, notadotacaoitem__ugr=unidade_gestora, tipo=None)
            )
            .distinct()
            .order_by('codigo')
        )
    else:
        return Evento.objects.filter(notadotacaoitem__isnull=False, tipo=None).distinct().order_by('codigo')


def get_eventos_desatualizados_notasempenho(unidade_gestora=None):
    """verifica nas notas de empenho se existe algum evento referenciado que não possui tipo definido"""
    if unidade_gestora:
        return Evento.objects.filter(notaempenho__isnull=False, notaempenho__emitente_ug=unidade_gestora, tipo=None).distinct().order_by('codigo')
    else:
        return Evento.objects.filter(notaempenho__isnull=False, tipo=None).distinct().order_by('codigo')


def get_eventos_desatualizados_notascreditodotacao(unidade_gestora=None):
    """verifica nas notas de crédito e dotação se existe algum evento referenciado que não possui tipo (crédito ou débito) definido"""
    enc = get_eventos_desatualizados_notascredito(unidade_gestora)
    end = get_eventos_desatualizados_notasdotacao(unidade_gestora)

    # quando o primeiro query returna nulo o retorno estava sendo nulo
    if enc:
        return enc | end
    else:
        return end
