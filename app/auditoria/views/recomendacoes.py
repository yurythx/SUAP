from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.template.defaultfilters import slugify

from auditoria.forms.documento import DocumentoDigitalizadoForm
from comum.utils import get_setor
from djtools.utils import get_datetime_now, httprr, permission_required, rtr
from documento_eletronico.forms import ListarDocumentosTextoForm
from documento_eletronico.models import DocumentoTexto

from ..forms import CancelarRecomendacaoForm, DescricaoRecomendacaoForm, MonitorarRecomendacaoForm, RemoverDocumentoManifestacaoForm
from ..models import HistoricoRecomendacao, Monitoramento, Recomendacao, RecomendacaoDocumento, RecomendacaoStatus
from ..notificacao import Notificar


@rtr('auditoria/templates/recomendacao/recomendacao.html')
@permission_required('comum.is_auditor')
def visualizar_recomendacao(request, recomendacao_id):
    recomendacao = get_object_or_404(Recomendacao, pk=recomendacao_id)
    recomendacao.verificar_expiracao()
    quantidade_documentos_removidos = RecomendacaoDocumento.objects.removidos().count()
    title = recomendacao
    monitoramentos = {monitoramento.unidade.id: monitoramento for monitoramento in recomendacao.monitoramentos.all()}
    eh_auditor = request.user.has_perm('comum.is_auditor') and request.user.has_group_cached(['Auditor'])
    if recomendacao.status not in RecomendacaoStatus.SITUACOES_INATIVAS:
        steps = '<ul class="steps">'
        for situacao, opcoes in RecomendacaoStatus.get_fluxo(recomendacao.status):
            if situacao == recomendacao.status:
                steps += f'<li><span class="step-{slugify(opcoes[1])} active">{opcoes[0]}</span></li>'
            else:
                steps += f'<li><span class="step-{slugify(opcoes[1])}">{opcoes[0]}</span></li>'
        steps += '</ul>'

    return locals()


def alterar_etapa_recomendacao(recomendacao, target_id, user):
    status = RecomendacaoStatus.get_status_description(target_id)
    _, transition_function = object.get_transition_to(user, target_id)
    #
    if transition_function is None:
        raise PermissionDenied
    #
    transition_function()
    object.save()
    HistoricoRecomendacao.objects.create(recomendacao=recomendacao, descricao=f'Alterou a situação da recomendação para: {status}')


@rtr('auditoria/templates/form.html')
@permission_required('comum.is_auditor')
def cancelar_recomendacao(request, recomendacao_id):
    recomendacao = get_object_or_404(Recomendacao, pk=recomendacao_id)
    title = f'Cancelar {recomendacao}'
    if not recomendacao.pode_cancelar(request.user):
        return httprr('..', 'Você não tem permissão para realizar essa ação.', tag='error')
    #
    form = CancelarRecomendacaoForm(request.POST or None, request=request, instance=recomendacao)
    if form.is_valid():
        with transaction.atomic():
            form.save()
            HistoricoRecomendacao.objects.create(recomendacao=recomendacao, descricao=f'Cancelou {recomendacao}')
        #
        return httprr('..', 'Recomendação cancelada com sucesso.')
    #
    return locals()


@permission_required('comum.is_auditor')
def consolidar_recomendacao(request, recomendacao_id):
    with transaction.atomic():
        return alterar_etapa_recomendacao(request, recomendacao_id, RecomendacaoStatus.CONSOLIDADA, request.user)


@rtr('auditoria/templates/form.html')
@permission_required('comum.is_auditor')
def monitorar_recomendacao(request, recomendacao_id):
    recomendacao = get_object_or_404(Recomendacao, pk=recomendacao_id)
    title = f'Monitorar {recomendacao}'
    target_url = recomendacao.get_absolute_url()
    form = MonitorarRecomendacaoForm(request.POST or None, recomendacao=recomendacao, request=request)
    if form.is_valid():
        try:
            with transaction.atomic():
                monitoramentos = form.processar()
                for monitoramento in monitoramentos:
                    Notificar.comunicacao_inicio_monitoramento(monitoramento)
                    descricao = f'Iniciou o monitoramento da unidade: {monitoramento.unidade}'
                    HistoricoRecomendacao.objects.create(recomendacao=recomendacao, descricao=descricao)
            #
            return httprr(target_url, 'Etapa alterada com sucesso.')
        except PermissionDenied:
            return httprr(target_url, 'Permissão negada.', tag='error')
    #
    return locals()


@permission_required('comum.is_auditor')
def iniciar_monitoramento_unidade(request, monitoramento_id):
    monitoramento = get_object_or_404(Monitoramento, pk=monitoramento_id)
    recomendacao = monitoramento.recomendacao
    unidade = monitoramento.unidade
    target_url = '..'
    form = MonitorarRecomendacaoForm(request.POST or None, recomendacao=recomendacao, request=request, unidade_id=unidade.id)
    if form.is_valid():
        try:
            with transaction.atomic():
                form.processar()
                Notificar.comunicacao_inicio_monitoramento(monitoramento)
                descricao = f'Iniciou o monitoramento da unidade: {unidade}'
                HistoricoRecomendacao.objects.create(recomendacao=recomendacao, descricao=descricao)
            #
            return httprr(target_url, 'Etapa alterada com sucesso.')
        except PermissionDenied:
            return httprr(target_url, 'Permissão negada.', tag='error')
    #
    return locals()


@permission_required('comum.is_auditor')
def reiniciar_monitoramento(request, recomendacao_id):
    recomendacao = get_object_or_404(Recomendacao, pk=recomendacao_id)
    title = f'Monitorar {recomendacao}'
    target_url = recomendacao.get_absolute_url()
    if not recomendacao.pode_editar(request.user) and recomendacao.cancelada:
        return httprr('..', 'Você não tem permissão para realizar essa ação.', tag='error')
    with transaction.atomic():
        recomendacao.reiniciar_monitoramento()
        recomendacao.save()
        HistoricoRecomendacao.objects.create(recomendacao=recomendacao, descricao=f'Reinicou a recomendação {recomendacao}')
        return httprr('..', 'Recomendação reiniciada com sucesso.')
    return locals()


@rtr('auditoria/templates/form.html')
@permission_required('comum.is_auditor')
def revisar_recomendacao(request, recomendacao_id):
    recomendacao = get_object_or_404(Recomendacao, pk=recomendacao_id)
    title = f'Revisar recomendação #{recomendacao}'
    if not recomendacao.pode_editar(request.user) and recomendacao.em_execucao:
        return httprr('..', 'Você não tem permissão para realizar essa ação.', tag='error')
    #
    form = DescricaoRecomendacaoForm(request.POST or None, request=request, recomendacao_id=recomendacao.id)
    if form.is_valid():
        with transaction.atomic():
            form.save()
            HistoricoRecomendacao.objects.create(recomendacao=recomendacao, descricao=f'Revisou a recomendação {recomendacao}')
        #
        return httprr('..', 'Recomendação editada com sucesso.')
    #
    return locals()


@rtr('processo_eletronico/templates/listar_documentos_adicionar.html')
@permission_required('comum.is_auditor')
def listar_documentos_anexar(request, recomendacao_id):
    instance = get_object_or_404(Recomendacao, pk=recomendacao_id)
    title = f'Documentos que podem ser adicionados à recomendação {instance}'
    label_add_documento = 'Adicionar à recomendação'
    is_anexar_documento = True
    exibir_dados_gerais = False
    aviso = 'Somente documentos finalizados poderão ser adicionados a uma recomendação.'
    exibir_tab_documentos_interno = True
    view_action = 'auditoria:anexar_documento_recomendacao'
    view_action_label = 'Adicionar à recomendação'
    initial = {}
    setor = get_setor(request.user)
    if setor and setor.uo:
        initial = {'campus': setor.uo.pk, 'setor': setor.pk, 'ano': get_datetime_now().year}
    filters = request.GET.copy()
    page = filters.pop('page', 0)
    data = initial if not filters else request.GET
    form = ListarDocumentosTextoForm(data, request=request)
    documentos, _, _, _ = form.processar()
    recomendacoes_ids = RecomendacaoDocumento.objects.filter(recomendacao=instance, removido_em__isnull=True).values_list('id', flat=True)
    documentos = documentos.exclude(id__in=recomendacoes_ids)
    documentos = documentos.finalizados().order_by('-data_ultima_modificacao')
    return locals()


@rtr()
@permission_required('comum.is_auditor')
def anexar_documento_recomendacao(request, recomendacao_id, documento_id):
    recomendacao: Recomendacao = get_object_or_404(Recomendacao, pk=recomendacao_id)
    documento: DocumentoTexto = get_object_or_404(DocumentoTexto, pk=documento_id)
    target_url = recomendacao.get_absolute_url()
    if not recomendacao.pode_editar(request.user):
        return httprr(target_url, 'Você não tem permissão para realizar essa ação.', tag='error')
    #
    recomendacao.adicionar_documento(documento, request.user)
    recomendacao.save()
    return httprr(target_url, 'Operação realizada com sucesso.')


@rtr()
@permission_required('comum.is_auditor')
def upload_documento_recomendacao(request, recomendacao_id):
    recomendacao: Recomendacao = get_object_or_404(Recomendacao, pk=recomendacao_id)
    title = f'Upload de Documento externo à {recomendacao}'
    target_url = recomendacao.get_absolute_url()
    if not recomendacao.pode_editar(request.user):
        return httprr(target_url, 'Você não tem permissão para realizar essa ação.', tag='error')
    #
    form = DocumentoDigitalizadoForm(request.POST or None, request.FILES or None, request=request)
    if form.is_valid():
        with transaction.atomic():
            documento = form.save()
            recomendacao.adicionar_documento(documento, request.user)
            recomendacao.save()
            return httprr(target_url, 'Documento anexado com sucesso.')
    return locals()


@rtr()
@permission_required('comum.is_auditor')
def remover_documento_recomendacao(request, recomendacao_documento_id):
    recomendacao_documento: RecomendacaoDocumento = get_object_or_404(RecomendacaoDocumento, pk=recomendacao_documento_id)
    recomendacao: Recomendacao = recomendacao_documento.recomendacao
    title = f'Remover Documento da recomendação {recomendacao_documento.recomendacao}'
    if not recomendacao.pode_remover_documento(request.user):
        return httprr('..', 'Você não tem permissão para realizar essa ação.', tag='error')
    #
    form = RemoverDocumentoManifestacaoForm(request.POST or None, instance=recomendacao_documento, request=request)
    if form.is_valid():
        form.save()
        return httprr('..', 'Documento removido com sucesso.')
    return locals()
