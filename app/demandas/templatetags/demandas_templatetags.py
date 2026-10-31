from django.template import Library
from django.utils.safestring import mark_safe
from demandas.models import Demanda, Situacao, Tag, TagDemandantes
from django.conf import settings

register = Library()


@register.filter()
def status_dashboard(situacao):
    if situacao == Situacao.ESTADO_ABERTO:
        return 'info'
    elif situacao in [Situacao.ESTADO_APROVADO, Situacao.ESTADO_HOMOLOGADA]:
        return 'success'
    elif situacao == Situacao.ESTADO_SUSPENSO:
        return 'error'
    elif situacao in [Situacao.ESTADO_EM_ANALISE, Situacao.ESTADO_EM_HOMOLOGACAO]:
        return 'caution'
    else:
        return 'warning'


@register.simple_tag()
def demandas_ativas_por_demandante(demandante):
    return Demanda.objects.ativas().filter(demandantes__in=[demandante])


@register.simple_tag()
def demandas_tags_por_demandante(demandante):
    tags_ids = TagDemandantes.objects.filter(demandantes=demandante).values_list('tag', flat=True)
    tags = Tag.objects.filter(id__in=tags_ids)
    return tags


@register.simple_tag()
def area_atuacao_tags_relacionadas(area_atuacao):
    lista = list("<ul class='tags with-link'>")
    for tag in area_atuacao.tags_relacionadas.all():
        lista.append(f'<li><a class="popup" href="/admin/demandas/tag/{tag.id}/change">{tag}</a></li>')
    lista.append('</ul>')
    return mark_safe(''.join(lista))


@register.simple_tag()
def demanda_situacao_status(demanda, extra_status_css=''):
    status = 'default'
    if demanda.situacao == Situacao.ESTADO_ABERTO:
        status = 'info'
    elif demanda.situacao in [Situacao.ESTADO_EM_NEGOCIACAO, Situacao.ESTADO_SUSPENSO]:
        status = 'warning'
    elif demanda.situacao == Situacao.ESTADO_CANCELADO:
        status = 'error'
    elif demanda.situacao in [Situacao.ESTADO_APROVADO, Situacao.ESTADO_HOMOLOGADA, Situacao.ESTADO_EM_IMPLANTACAO, Situacao.ESTADO_CONCLUIDO]:
        status = 'success'
    elif demanda.situacao in [Situacao.ESTADO_EM_ANALISE, Situacao.ESTADO_EM_DESENVOLVIMENTO, Situacao.ESTADO_EM_HOMOLOGACAO]:
        status = 'caution'
    return mark_safe(f'<span class="status status-{status} {extra_status_css}">{demanda.get_situacao_display()}</span>')


@register.simple_tag()
def erro_situacao_status(erro, extra_status_css=''):

    if 'erros' in settings.INSTALLED_APPS:
        from erros.models import Erro

        status = 'default'
        if erro.situacao in [Erro.SITUACAO_ABERTO, Erro.SITUACAO_REABERTO]:
            status = 'info'
        elif erro.situacao == Erro.SITUACAO_EM_ANALISE:
            status = 'warning'
        elif erro.situacao == Erro.SITUACAO_CANCELADO:
            status = 'error'
        elif erro.situacao == Erro.SITUACAO_RESOLVIDO:
            status = 'success'
        elif erro.situacao in [Erro.SITUACAO_EM_CORRECAO, Erro.SITUACAO_AGUARDANDO_FEEDBACK]:
            status = 'caution'
        return mark_safe(f'<span class="status status-{status} {extra_status_css}">{erro.get_situacao_display()}</span>')
    return ''
