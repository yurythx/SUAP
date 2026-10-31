from django.http import HttpRequest
from django.template.defaultfilters import pluralize
from django.urls import reverse_lazy

from auditoria.models.monitoramento import IndicacaoServidorMonitoramento
from auditoria.models.posicionamento import Posicionamento
from djtools import layout
from django.db.models import OuterRef, Exists

# Local imports
from ..models import Manifestacao, Monitoramento, Recomendacao, SolicitacaoProvidencia
from ..utils import setores_que_respondo_como_chefe


@layout.atribuidos_a_mim()
def index_auditor_recomendacoes_a_monitorar(request):
    pendencias = []
    app_label = Recomendacao._meta.app_label
    model_name = Recomendacao._meta.model_name
    url = f'{reverse_lazy(f"admin:{app_label}_{model_name}_changelist")}?tab=tab_minhas_recomendacoes_a_monitorar'
    auditor = request.user.get_vinculo()
    #
    recomendacoes = Monitoramento.objects.recomendacoes_a_monitorar()
    recomendacoes_a_monitorar = recomendacoes.filter(monitor=auditor)
    qtd = recomendacoes_a_monitorar.count()
    if qtd:
        titulo = f'Recomendaç{pluralize(qtd, "ão,ões")} de auditoria'
        subtitulo = 'a monitorar'
        pendencias.append({'titulo': titulo, 'subtitulo': subtitulo, 'qtd': qtd, 'url': url})
    return pendencias


@layout.atribuidos_a_mim()
def index_auditor_recomendacoes_a_analisar(request):
    pendencias = []
    auditor = request.user.get_vinculo()
    # Minhas Recomendacoes
    manifestacoes_pendentes_subquery = Manifestacao.objects.aguardando_analise().filter(monitoramento=OuterRef('pk'))
    monitoramentos = (
        Monitoramento.objects.em_monitoramento()
        .filter(recomendacao__monitor=auditor)
        .annotate(possui_manifestacoes_pendentes=Exists(manifestacoes_pendentes_subquery))
        .filter(possui_manifestacoes_pendentes=True)
    )
    # Manifestações a receber
    manifestacoes_a_receber = Manifestacao.objects.aguardando_analise().filter(monitoramento__in=monitoramentos)
    qtd = manifestacoes_a_receber.count()
    app_label = Monitoramento._meta.app_label
    model_name = Monitoramento._meta.model_name
    url = f'{reverse_lazy(f"admin:{app_label}_{model_name}_changelist")}?tab=tab_manifestacoes_a_analisar'
    if qtd:
        titulo = f'Manifestaç{pluralize(qtd, "ão,ões")} de auditoria'
        subtitulo = 'a analisar'
        pendencias.append({'titulo': titulo, 'subtitulo': subtitulo, 'qtd': qtd, 'url': url})
    return pendencias


@layout.atribuidos_a_mim()
def index_auditor_revisor(request):
    pendencias = []
    auditor = request.user.get_vinculo()
    recomendacoes = Monitoramento.objects.recomendacoes_a_monitorar()
    recomendacoes_a_revisar = recomendacoes.filter(revisor=auditor)
    qtd = recomendacoes_a_revisar.count()
    if qtd:
        app_label = Recomendacao._meta.app_label
        model_name = Recomendacao._meta.model_name
        url = reverse_lazy(f'admin:{app_label}_{model_name}_changelist')
        titulo = f'Recomendaç{pluralize(qtd, "ão,ões")} de auditoria'
        subtitulo = 'a revisar'
        pendencias.append({'titulo': titulo, 'subtitulo': subtitulo, 'qtd': qtd, 'url': url})
    return pendencias


@layout.atribuidos_a_mim()
def index_novas_solicitacoes_ao_auditado(request):
    pendencias = []
    setores = setores_que_respondo_como_chefe(request.user)
    solicitacoes = SolicitacaoProvidencia.objects.aguardando_ciencia().filter(setor__in=setores)
    qtd = solicitacoes.count()
    if qtd:
        url = reverse_lazy('auditoria:meus_monitoramentos', current_app='auditoria')
        titulo = f'Recomendaç{pluralize(qtd, "ão,ões")} de auditoria'
        subtitulo = 'a responder'
        pendencias.append({'titulo': titulo, 'subtitulo': subtitulo, 'qtd': qtd, 'url': url})
    return pendencias


@layout.atribuidos_a_mim()
def index_indicacoes_para_monitoramento(request):
    pendencias = []
    indicacoes = IndicacaoServidorMonitoramento.objects.pendentes()
    indicacoes = indicacoes.filter(servidor=request.user.get_vinculo())
    qtd = indicacoes.count()
    if qtd:
        url = reverse_lazy('auditoria:meus_monitoramentos', current_app='auditoria')
        titulo = f'Recomendaç{pluralize(qtd, "ão,ões")} de auditoria'
        subtitulo = 'a responder'
        pendencias.append({'titulo': titulo, 'subtitulo': subtitulo, 'qtd': qtd, 'url': url})
    return pendencias


@layout.atribuidos_a_mim()
def index_manifestacoes_nao_enviadas(request):
    pendencias = []
    setores = setores_que_respondo_como_chefe(request.user)
    monitoramentos_ids = Monitoramento.objects.filter(unidade__in=setores).values_list('id', flat=True)
    manifestacoes = Manifestacao.objects.filter(monitoramento_id__in=monitoramentos_ids).manifestacoes_a_enviar()
    qtd = manifestacoes.count()
    if qtd:
        url = reverse_lazy('auditoria:manifestacoes_a_enviar', current_app='auditoria')
        titulo = f'Manifestaç{pluralize(qtd, "ão,ões")} de auditoria'
        subtitulo = 'a enviar'
        pendencias.append({'titulo': titulo, 'subtitulo': subtitulo, 'qtd': qtd, 'url': url})
    return pendencias


@layout.atribuidos_a_meus_grupos()
def index_manifestacoes_pendentes(request: HttpRequest) -> list[dict]:
    pendencias = []
    vinculo = request.user.get_vinculo()
    monitoramentos_ids = list(IndicacaoServidorMonitoramento.objects.filter(servidor=vinculo).values_list('monitoramento', flat=True))
    if not monitoramentos_ids:
        return pendencias
    qtd = Manifestacao.objects.filter(monitoramento_id__in=monitoramentos_ids).manifestacoes_a_enviar().count()
    if qtd:
        url = reverse_lazy('auditoria:manifestacoes_pendentes', current_app='auditoria')
        titulo = f'Manifestaç{pluralize(qtd, "ão,ões")}'
        subtitulo = f'pendente{pluralize(qtd)}'
        pendencias.append({'titulo': titulo, 'subtitulo': subtitulo, 'qtd': qtd, 'url': url})
    return pendencias


@layout.atribuidos_a_mim()
def index_novos_posicionamentos_auditoria(request):
    pendencias = []
    setores = setores_que_respondo_como_chefe(request.user)
    posicionamentos = Posicionamento.objects.filter(manifestacao__monitoramento__unidade__in=setores, ciencia_em__isnull=True)
    qtd = posicionamentos.count()
    if qtd:
        url = reverse_lazy('auditoria:meus_monitoramentos', current_app='auditoria')
        singular_ou_plural = pluralize(qtd, 'o,os')
        titulo = f'Posicionament{singular_ou_plural} de auditoria'
        subtitulo = f'pendente{pluralize(qtd)}'
        pendencias.append({'titulo': titulo, 'subtitulo': subtitulo, 'qtd': qtd, 'url': url})
    return pendencias
