from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Exists, OuterRef, Prefetch, Q
from django.shortcuts import get_object_or_404

from auditoria.models.manifestacao import Manifestacao
from auditoria.models.posicionamento import PosicionamentoStatus
from auditoria.models.recomendacao import Recomendacao
from djtools.templatetags.filters import format_
from djtools.utils import get_datetime_now, httprr, permission_required, rtr
from rh.models import Setor

from ..forms import (
    CancelarMonitoramentoForm,
    DesignarServidorMonitoramentoForm,
    FinalizarMonitoramentoForm,
    SetorFilterForm,
    SolicitacaoProvidenciaForm,
)
from ..models import IndicacaoServidorMonitoramento, Monitoramento, MonitoramentoStatus, Posicionamento, Relatorio
from ..tasks import recomendacoes_por_setor_to_xls
from ..utils import setores_que_respondo_como_chefe


def get_meus_monitoramentos(user, status_filter=MonitoramentoStatus.EM_MONITORAMENTO):
    """
    Retorna os monitoramentos que o usuário pode visualizar.
    """
    setores = setores_que_respondo_como_chefe(user)
    vinculo = user.get_vinculo()
    filtro_monitoramento = Q(unidade__in=setores) | Q(indicacoes__servidor=vinculo, indicacoes__revogada=False)
    return Monitoramento.objects.emitidos().filter(filtro_monitoramento, status=status_filter)


def get_meus_monitoramentos_por_relatorio(relatorio, user, status_filter=MonitoramentoStatus.EM_MONITORAMENTO):
    meus_monitoramentos = get_meus_monitoramentos(user, status_filter)
    return meus_monitoramentos.filter(recomendacao__relatorio=relatorio)


@rtr('auditoria/templates/monitoramento/meus_monitoramentos.html')
@login_required()
def monitoramentos(request):
    title = 'Recomendações de Auditoria'
    setores = setores_que_respondo_como_chefe(request.user)
    vinculo = request.user.get_vinculo()
    filtro_monitoramento = Q(unidade__in=setores) | Q(indicacoes__servidor=vinculo, indicacoes__revogada=False)
    monitoramentos = Monitoramento.objects.emitidos().filter(filtro_monitoramento)
    ids = monitoramentos.values_list('recomendacao__relatorio__id', flat=True).distinct()
    today = get_datetime_now().date()
    em_7_dias = today + timedelta(days=7)
    # Filtrar os relatórios e adicionar as contagens de monitoramentos por status
    flt = Q(recomendacoes__monitoramentos__unidade__in=setores) | Q(
        recomendacoes__monitoramentos__indicacoes__servidor=vinculo, recomendacoes__monitoramentos__indicacoes__revogada=False
    )

    meus_relatorios = (
        Relatorio.objects.filter(id__in=ids)
        .annotate(
            total_monitoramentos=Count('recomendacoes__monitoramentos__id', filter=flt, distinct=True),
            em_andamento=Count(
                'recomendacoes__monitoramentos__id',
                filter=flt & Q(recomendacoes__monitoramentos__status=MonitoramentoStatus.EM_MONITORAMENTO),
                distinct=True,
            ),
            concluidos=Count(
                'recomendacoes__monitoramentos__id',
                filter=flt & Q(recomendacoes__monitoramentos__status=MonitoramentoStatus.CONCLUIDO),
                distinct=True,
            ),
            finalizados=Count(
                'recomendacoes__monitoramentos__id',
                filter=flt & Q(recomendacoes__monitoramentos__status=MonitoramentoStatus.FINALIZADO),
                distinct=True,
            ),
            cancelados=Count(
                'recomendacoes__monitoramentos__id',
                filter=flt & Q(recomendacoes__monitoramentos__status=MonitoramentoStatus.CANCELADO),
                distinct=True,
            ),
            vencidos=Count(
                'recomendacoes__monitoramentos__id',
                filter=flt
                & Q(recomendacoes__monitoramentos__status=MonitoramentoStatus.EM_MONITORAMENTO)
                & Q(recomendacoes__monitoramentos__ultima_solicitacao__prazo_atual__lt=today),
                distinct=True,
            ),
            vencendo_em_sete_dias=Count(
                'recomendacoes__monitoramentos__id',
                filter=flt
                & Q(recomendacoes__monitoramentos__status=MonitoramentoStatus.EM_MONITORAMENTO)
                & Q(recomendacoes__monitoramentos__ultima_solicitacao__prazo_atual__gte=today)
                & Q(recomendacoes__monitoramentos__ultima_solicitacao__prazo_atual__lte=em_7_dias),
                distinct=True,
            ),
            possui_monitoramento_setor=Exists(Monitoramento.objects.filter(recomendacao=OuterRef('recomendacoes__id')).filter(filtro_monitoramento)),
        )
        .filter(possui_monitoramento_setor=True)
        .prefetch_related(
            Prefetch(
                'recomendacoes__monitoramentos',
                queryset=Monitoramento.objects.filter(filtro_monitoramento)
                .annotate(
                    tem_posicionamento_nao_lido=Exists(
                        Posicionamento.objects.filter(
                            status=PosicionamentoStatus.PUBLICADO, manifestacao__monitoramento=OuterRef('pk'), ciencia_em__isnull=True
                        )
                    ),
                    tem_manifestacao_a_enviar=Exists(Manifestacao.objects.registradas().filter(monitoramento=OuterRef('pk'))),
                )
                .distinct(),
            )
        )
    )
    return locals()


@rtr('auditoria/templates/monitoramento/monitoramentos.html')
@login_required()
def monitoramentos_expirados(request, relatorio_id):
    relatorio = get_object_or_404(Relatorio, pk=relatorio_id)
    title = 'Recomendações Expiradas'
    hoje = get_datetime_now().date()
    monitoramentos = get_meus_monitoramentos_por_relatorio(relatorio, request.user)
    monitoramentos = monitoramentos.filter(ultima_solicitacao__prazo_atual__lt=hoje).select_related('ultima_solicitacao', 'unidade', 'recomendacao')
    return locals()


@rtr('auditoria/templates/monitoramento/monitoramentos.html')
@login_required()
def monitoramentos_expirando(request, relatorio_id):
    relatorio = get_object_or_404(Relatorio, pk=relatorio_id)
    title = 'Recomendações Expirando em 7 dias'
    hoje = get_datetime_now().date()
    sete_dias = hoje + timedelta(days=7)
    monitoramentos = get_meus_monitoramentos_por_relatorio(relatorio, request.user)
    monitoramentos = monitoramentos.filter(ultima_solicitacao__prazo_atual__gte=hoje, ultima_solicitacao__prazo_atual__lte=sete_dias).select_related(
        'ultima_solicitacao', 'unidade', 'recomendacao'
    )

    return locals()


@rtr('auditoria/templates/monitoramento/monitoramentos.html')
@login_required()
def monitoramentos_em_monitoramento(request, relatorio_id):
    title = 'Recomendações em Monitoramento'
    relatorio = get_object_or_404(Relatorio, pk=relatorio_id)
    monitoramentos = get_meus_monitoramentos_por_relatorio(relatorio, request.user, MonitoramentoStatus.EM_MONITORAMENTO)
    return locals()


@rtr('auditoria/templates/monitoramento/monitoramentos.html')
@login_required()
def monitoramentos_cancelados(request, relatorio_id):
    title = 'Recomendações Canceladas'
    relatorio = get_object_or_404(Relatorio, pk=relatorio_id)
    monitoramentos = get_meus_monitoramentos_por_relatorio(relatorio, request.user, MonitoramentoStatus.CANCELADO)
    return locals()


@rtr('auditoria/templates/monitoramento/monitoramentos.html')
@login_required()
def monitoramentos_finalizados(request, relatorio_id):
    title = 'Recomendações Finalizadas'
    relatorio = get_object_or_404(Relatorio, pk=relatorio_id)
    monitoramentos = get_meus_monitoramentos_por_relatorio(relatorio, request.user, MonitoramentoStatus.FINALIZADO)
    return locals()


@rtr('auditoria/templates/monitoramento/monitoramentos.html')
@login_required()
def monitoramentos_concluidos(request, relatorio_id):
    title = 'Recomendações Concluídas'
    relatorio = get_object_or_404(Relatorio, pk=relatorio_id)
    monitoramentos = get_meus_monitoramentos_por_relatorio(relatorio, request.user, MonitoramentoStatus.CONCLUIDO)
    return locals()


@rtr('auditoria/templates/monitoramento/monitoramento.html')
@login_required()
def visualizar_monitoramento(request, monitoramento_id):
    monitoramento: Monitoramento = get_object_or_404(Monitoramento, pk=monitoramento_id)
    if monitoramento.pode_visualizar_monitoramento(request.user):
        monitoramento.notificar_acesso(request.user)
        recomendacao = monitoramento.recomendacao
        title = str(recomendacao)
        indicacao = IndicacaoServidorMonitoramento.objects.filter(monitoramento=monitoramento, servidor=request.user.get_vinculo()).first()
        if indicacao:
            indicacao.marcar_como_visualizado()

        return locals()
    return httprr('..', 'Você não tem permissão para realizar essa ação.', tag='error')


@rtr('auditoria/templates/form.html')
@permission_required('comum.is_auditor')
def enviar_solicitacao_providencia(request, monitoramento_id):
    monitoramento = get_object_or_404(Monitoramento, pk=monitoramento_id)
    title = 'Enviar solicitação de providências'
    target_url = monitoramento.recomendacao.get_absolute_url()
    if not monitoramento.pode_enviar_solicitacao(request.user):
        return httprr('..', 'Você não tem permissão para realizar essa ação.', tag='error')
    form = SolicitacaoProvidenciaForm(request.POST or None, request=request, monitoramento=monitoramento)
    if form.is_valid():
        form.save()
        return httprr(target_url, 'Solicitação enviada com sucesso.')
    return locals()


@rtr('auditoria/templates/form.html')
@permission_required('comum.is_auditor')
def cancelar_monitoramento(request, monitoramento_id):
    monitoramento = get_object_or_404(Monitoramento, pk=monitoramento_id)
    title = 'Cancelar monitoramento'
    if not monitoramento.pode_cancelar(request.user):
        return httprr('..', 'Você não tem permissão para realizar essa ação.', tag='error')
    form = CancelarMonitoramentoForm(request.POST or None, request=request, instance=monitoramento)
    if form.is_valid():
        form.save()
        return httprr('..', 'monitoramento cancelado com sucesso.')
    return locals()


@rtr('auditoria/templates/form.html')
@permission_required('comum.is_auditor')
def finalizar_monitoramento(request, monitoramento_id):
    monitoramento = get_object_or_404(Monitoramento, pk=monitoramento_id)
    title = 'Finalizar monitoramento'
    if not monitoramento.pode_finalizar(request.user):
        return httprr('..', 'Você não tem permissão para realizar essa ação.', tag='error')
    form = FinalizarMonitoramentoForm(request.POST or None, request=request, monitoramento=monitoramento)
    if form.is_valid():
        form.processar()
        return httprr('..', 'Monitoramento Finalizado com sucesso.')
    return locals()


@rtr('auditoria/templates/relatorios/monitoramentos_por_setor.html')
@permission_required('comum.is_auditor')
def monitoramentos_por_unidade(request):
    title = 'Recomendações por Setor'
    form = SetorFilterForm(request.GET or None)
    setores = Setor.objects.suap_ativos().all()
    if form.is_valid():
        setor = form.cleaned_data.get('setor')
        campus = form.cleaned_data.get('campus')
        if campus:
            setores = setores.filter(uo=campus)
        if setor:
            setores = setores.filter(id=setor.id)

    setores = (
        setores.annotate(
            total_registrados=Count('monitoramento', filter=Q(monitoramento__status=MonitoramentoStatus.REGISTRADO)),
            total_em_monitoramento=Count('monitoramento', filter=Q(monitoramento__status=MonitoramentoStatus.EM_MONITORAMENTO)),
            total_concluidos=Count('monitoramento', filter=Q(monitoramento__status=MonitoramentoStatus.CONCLUIDO)),
            total_finalizados=Count('monitoramento', filter=Q(monitoramento__status=MonitoramentoStatus.FINALIZADO)),
            total_em_revisao=Count('monitoramento', filter=Q(monitoramento__status=MonitoramentoStatus.EM_REVISAO)),
            total_revisados=Count('monitoramento', filter=Q(monitoramento__status=MonitoramentoStatus.REVISADO)),
        )
        .order_by('-total_em_monitoramento', '-total_registrados', '-total_concluidos', '-total_finalizados')
        .filter(
            Q(total_registrados__gt=0)
            | Q(total_em_monitoramento__gt=0)
            | Q(total_concluidos__gt=0)
            | Q(total_finalizados__gt=0)
            | Q(total_em_revisao__gt=0)
            | Q(total_revisados__gt=0)
        )
        .distinct()
    )

    if 'xls' in request.GET:
        setores_data = [
            {
                'setor': format_(setor.sigla),
                'campus': format_(setor.uo),
                'total_em_monitoramento': setor.total_em_monitoramento,
                'total_registrados': setor.total_registrados,
                'total_concluidos': setor.total_concluidos,
                'total_finalizados': setor.total_finalizados,
                'total_em_revisao': setor.total_em_revisao,
                'total_revisados': setor.total_revisados,
            }
            for setor in setores
        ]
        return recomendacoes_por_setor_to_xls(setores_data)

    return locals()


@rtr('auditoria/templates/form.html')
@permission_required('comum.is_chefe_de_setor')
def designar_servidor_para_monitoramento(request, monitoramento_id):
    monitoramento = get_object_or_404(Monitoramento, pk=monitoramento_id)
    recomendacao = monitoramento.recomendacao
    title = f'Designar Servidores para {recomendacao}'
    target_url = monitoramento.get_absolute_url()
    if not monitoramento.pode_designar_servidor(request.user):
        return httprr(target_url, 'Você não tem permissão para realizar essa ação ou um servidor já foi indicado.', tag='error')
    form = DesignarServidorMonitoramentoForm(request.POST or None, request=request, monitoramento=monitoramento)
    if form.is_valid():
        form.save()
        return httprr(target_url, 'Servidor designado com sucesso.')
    return locals()


@rtr()
@permission_required('comum.is_chefe_de_setor')
def revogar_indicacao_monitoramento(request, indicacao_id):
    indicacao: IndicacaoServidorMonitoramento = get_object_or_404(IndicacaoServidorMonitoramento, pk=indicacao_id)
    monitoramento: Monitoramento = indicacao.monitoramento
    target_url = f'{monitoramento.get_absolute_url()}?tab=indicacoes'
    if not monitoramento.pode_editar_manifestacoes(request.user):
        return httprr(target_url, 'Você não tem permissão para realizar essa ação.', tag='error')
    #
    indicacao.revogar(request.user)
    indicacao.save()
    return httprr(target_url, 'Permissão removida com sucesso')


@rtr()
@login_required()
def concluir_indicacao_monitoramento(request, indicacao_id):
    indicacao: IndicacaoServidorMonitoramento = get_object_or_404(IndicacaoServidorMonitoramento, pk=indicacao_id)
    monitoramento: Monitoramento = indicacao.monitoramento
    target_url = f'{monitoramento.get_absolute_url()}?tab=indicacoes'
    if not indicacao.pode_concluir(request.user):
        return httprr(target_url, 'Você não tem permissão para realizar essa ação.', tag='error')
    #
    indicacao.marcar_tarefa_como_realizada()
    return httprr(target_url, 'Tarefa concluída com sucesso')


@rtr()
@login_required()
def remover_monitoramento(request, monitoramento_id):
    monitoramento: Monitoramento = get_object_or_404(Monitoramento, pk=monitoramento_id)
    recomendacao: Recomendacao = monitoramento.recomendacao
    target_url = f'{monitoramento.recomendacao.get_absolute_url()}?tab=indicacoes'
    if not monitoramento.pode_excluir(request.user):
        return httprr(target_url, 'Você não tem permissão para realizar essa ação.', tag='error')
    #
    with transaction.atomic():
        setor_auditado = monitoramento.unidade
        recomendacao.unidades.remove(setor_auditado)
        monitoramento.delete()
    return httprr(target_url, 'Tarefa concluída com sucesso')
