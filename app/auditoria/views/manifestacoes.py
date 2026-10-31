from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from django.template.defaultfilters import slugify
from django.urls import reverse_lazy

from auditoria.models.historico import HistoricoRecomendacao
from auditoria.models.monitoramento import IndicacaoServidorMonitoramento
from auditoria.notificacao import Notificar
from comum.utils import get_setor
from djtools.utils import get_datetime_now, httprr, permission_required, rtr
from documento_eletronico.forms import ListarDocumentosTextoForm
from documento_eletronico.models import DocumentoTexto

from ..forms import (
    ManifestacaoDocumentoDigitalizadoForm,
    ManifestacaoFormFactory,
    MonitoramentoManifestacaoForm,
    ReclassificarManifestacaoForm,
    RemoverDocumentoManifestacaoForm,
    SolicitarProrrogacaoManifestacaoForm,
)
from ..models import Manifestacao, ManifestacaoDocumento, ManifestacaoStatus, Monitoramento
from ..utils import setores_que_respondo_como_chefe


@rtr('auditoria/templates/manifestacao/manifestacao.html')
@login_required()
def visualizar_manifestacao(request, manifestacao_id):
    manifestacao: Manifestacao = get_object_or_404(Manifestacao, id=manifestacao_id)
    if not manifestacao.pode_visualizar(request.user):
        return httprr('..', 'Você não tem permissão para realizar essa ação.', tag='error')
    title = f'{manifestacao}'
    numero_documentos = manifestacao.documentos.nao_removidos().count()
    eh_auditor = request.user.has_perm('comum.is_auditor') and request.user.has_group_cached(['Auditor'])
    steps = '<ul class="steps">'
    for situacao, opcoes in list(ManifestacaoStatus.SITUACOES_FLUXO.items()):
        if situacao == manifestacao.status:
            steps += f'<li><span class="step-{slugify(opcoes[1])} active">{opcoes[0]}</span></li>'
        else:
            steps += f'<li><span class="step-{slugify(opcoes[1])}">{opcoes[0]}</span></li>'
    steps += '</ul>'
    return locals()


@rtr('auditoria/templates/form.html')
@login_required()
def editar_manifestacao(request, manifestacao_id):
    manifestacao: Manifestacao = get_object_or_404(Manifestacao, id=manifestacao_id)
    if not manifestacao.pode_editar_manifestacao(request.user):
        return httprr('..', 'Você não tem permissão para realizar essa ação.', tag='error')
    title = f'{manifestacao}'
    form = ManifestacaoFormFactory(request=request, manifestacao=manifestacao)
    if form.is_valid():
        instance = form.save()
        return httprr(instance.get_absolute_url(), 'Manifestação adicionada com sucesso.')
    #
    return locals()


@rtr()
@login_required()
def entregar_manifestacao(request, manifestacao_id):
    manifestacao: Manifestacao = get_object_or_404(Manifestacao, id=manifestacao_id)
    target_url = manifestacao.get_absolute_url()
    if not manifestacao.pode_enviar(request.user):
        return httprr(target_url, 'Você não tem permissão para realizar essa ação.', tag='error')
    #
    manifestacao.enviar(request.user)
    with transaction.atomic():
        manifestacao.save()
        Notificar.notificar_manifestacao(manifestacao)
    return httprr(target_url, 'Manifestação enviada para análise com sucesso.')


@rtr()
@permission_required('comum.is_auditor')
def receber_manifestacao(request, manifestacao_id):
    manifestacao = get_object_or_404(Manifestacao, id=manifestacao_id)
    target_url = manifestacao.get_absolute_url()
    if not manifestacao.pode_receber(request.user):
        return httprr(target_url, 'Você não tem permissão para realizar essa ação.', tag='error')
    #
    manifestacao.receber(request.user)
    manifestacao.save()
    return httprr(target_url, 'Manifestação recebida com sucesso.')


@rtr('auditoria/templates/monitoramento/adicionar_manifestacao.html')
@login_required()
def adicionar_manifestacao_monitoramento(request, monitoramento_id):
    monitoramento: Monitoramento = get_object_or_404(Monitoramento, pk=monitoramento_id)
    if not monitoramento.pode_adicionar_manifestacao(request.user):
        url = reverse_lazy('auditoria:visualizar_monitoramento', kwargs={'monitoramento_id': monitoramento.pk})
        return httprr(url, 'Você não tem permissão para realizar essa ação.', tag='error')
    #
    form = MonitoramentoManifestacaoForm(request.POST or None, request=request, monitoramento=monitoramento)
    title = 'Adicionar Manifestação'
    if form.is_valid():
        instance = form.save()
        return httprr(instance.get_absolute_url(), 'Manifestação adicionada com sucesso.')
    #
    return locals()


@rtr()
@login_required()
def solicitar_prorrogacao_manifestacao(request, monitoramento_id):
    monitoramento: Monitoramento = get_object_or_404(Monitoramento, pk=monitoramento_id)
    target_url = reverse_lazy('auditoria:visualizar_monitoramento', kwargs={'monitoramento_id': monitoramento.pk})
    if not monitoramento.pode_adicionar_manifestacao(request.user):
        return httprr(target_url, 'Você não tem permissão para realizar essa ação.', tag='error')

    title = 'Solicitar prorrogação de prazo'
    form = SolicitarProrrogacaoManifestacaoForm(request.POST or None, request=request, monitoramento=monitoramento)

    if form.is_valid():
        with transaction.atomic():
            form.save()
        #
        return httprr(target_url, "Manifestação registrada. Anexe documentos se necessário e clique em 'Enviar manifestação' para concluir.")
    #
    return locals()


@rtr('processo_eletronico/templates/listar_documentos_adicionar.html')
@login_required()
def listar_manifestacoes_anexar(request, manifestacao_id):
    instance = get_object_or_404(Manifestacao, pk=manifestacao_id)
    title = f'Documentos que podem ser adicionados ao relatório {instance}'
    label_add_documento = 'Adicionar ao relatório'
    is_anexar_documento = True
    exibir_dados_gerais = False
    aviso = 'Somente documentos finalizados poderão ser adicionados a um relatório.'
    exibir_tab_documentos_interno = True
    view_action = 'auditoria:anexar_documento_manifestacao'
    view_action_label = 'Adicionar à manifestação'
    initial = {}
    setor = get_setor(request.user)
    if setor and setor.uo:
        initial = {'campus': setor.uo.pk, 'setor': setor.pk, 'ano': get_datetime_now().year}
    filters = request.GET.copy()
    page = filters.pop('page', 0)
    data = initial if not filters else request.GET
    form = ListarDocumentosTextoForm(data, request=request)
    documentos, documentos_compartilhados, params, order_str = form.processar()
    manifestacoes_ids = ManifestacaoDocumento.objects.filter(manifestacao=instance, removido_em__isnull=True).values_list('id', flat=True)
    documentos.exclude(id__in=manifestacoes_ids)
    documentos = documentos.finalizados().order_by('-data_ultima_modificacao')
    return locals()


@rtr()
@login_required()
def anexar_documento_manifestacao(request, manifestacao_id, documento_id):
    manifestacao: Manifestacao = get_object_or_404(Manifestacao, pk=manifestacao_id)
    documento: DocumentoTexto = get_object_or_404(DocumentoTexto, pk=documento_id)
    target_url = manifestacao.get_absolute_url()
    if not manifestacao.pode_adicionar_documento(request.user):
        return httprr(target_url, 'Você não tem permissão para realizar essa ação.', tag='error')
    #
    manifestacao.adicionar_documento(documento, request.user)
    manifestacao.save()
    return httprr(target_url, 'Operação realizada com sucesso.')


@rtr()
@login_required()
def upload_documento_manifestacao(request, manifestacao_id):
    manifestacao: Manifestacao = get_object_or_404(Manifestacao, pk=manifestacao_id)
    title = f'Upload de Documento externo à {manifestacao}'
    target_url = manifestacao.get_absolute_url()
    if not manifestacao.pode_adicionar_documento(request.user):
        return httprr(target_url, 'Você não tem permissão para realizar essa ação.', tag='error')
    #
    form = ManifestacaoDocumentoDigitalizadoForm(request.POST or None, request.FILES or None, request=request)
    if form.is_valid():
        with transaction.atomic():
            documento = form.save()
            manifestacao.adicionar_documento(documento, request.user)
            manifestacao.save()
            return httprr(target_url, 'Documento anexado com sucesso.')
    return locals()


@rtr()
@login_required()
def remover_documento_manifestacao(request, manifestacao_documento_id):
    manifestacao_documento: ManifestacaoDocumento = get_object_or_404(ManifestacaoDocumento, pk=manifestacao_documento_id)
    manifestacao: Manifestacao = manifestacao_documento.manifestacao
    title = f'Remover Documento da manifestação {manifestacao_documento.manifestacao}'
    if not manifestacao.pode_remover_documento(request.user):
        return httprr('..', 'Você não tem permissão para realizar essa ação.', tag='error')
    #
    form = RemoverDocumentoManifestacaoForm(request.POST or None, instance=manifestacao_documento, request=request)
    if form.is_valid():
        form.save()
        return httprr('..', 'Documento removido com sucesso.')
    return locals()


@login_required()
def remover_manifestacao(request, manifestacao_id):
    manifestacao: Manifestacao = get_object_or_404(Manifestacao, pk=manifestacao_id)
    target_url = manifestacao.get_content_object_url(request.user)
    if not manifestacao.pode_remover(request.user):
        return httprr(target_url, 'Você não tem permissão para realizar essa ação.', tag='error')
    #
    monitoramento: Monitoramento = manifestacao.monitoramento
    try:
        with transaction.atomic():
            if manifestacao.solicitacao_providencia.aguardando_posicionamento:
                manifestacao.solicitacao_providencia.reabrir_para_ciencia()
                manifestacao.solicitacao_providencia.save()
            msg = (f'Removou a manifestação {manifestacao} do tipo {manifestacao.get_tipo_display()} ',)
            manifestacao.delete()
            HistoricoRecomendacao.objects.create(recomendacao=monitoramento.recomendacao, descricao=msg)
            return httprr(target_url, 'Manifestação removida com sucesso.')
    except Exception:
        return httprr(target_url, 'A operação falhou. Se o erro persistir, abra uma chamado.', tag='error')


@rtr('auditoria/templates/form.html')
@permission_required('comum.is_auditor')
def reclassificar_manifestacao(request, manifestacao_id):
    manifestacao: Manifestacao = get_object_or_404(Manifestacao, pk=manifestacao_id)
    target_url = manifestacao.get_absolute_url()
    if not manifestacao.pode_reclassificar(request.user):
        return httprr(target_url, 'Você não tem permissão para realizar essa ação.', tag='error')
    #
    form = ReclassificarManifestacaoForm(request.POST or None, request=request, instance=manifestacao)
    if form.is_valid():
        form.save()
        return httprr('..', 'Manifestação reclassificada com sucesso.')
    return locals()


@rtr('auditoria/templates/manifestacao/manifestacoes_a_enviar.html')
@permission_required('comum.is_chefe_de_setor')
def manifestacoes_a_enviar(request):
    title = 'Manifestaçãos a enviar para Auditoria'
    setores = setores_que_respondo_como_chefe(request.user)
    ids = Monitoramento.objects.filter(unidade__in=setores).values_list('id', flat=True)
    manifestacoes = Manifestacao.objects.filter(monitoramento_id__in=ids).manifestacoes_a_enviar()
    return locals()


@rtr('auditoria/templates/manifestacao/manifestacoes_a_enviar.html')
@login_required()
def manifestacoes_pendentes(request: HttpRequest) -> dict:
    title = 'Manifestaçãos a enviar para Auditoria'
    vinculo = request.user.get_vinculo()
    monitoramentos_ids = IndicacaoServidorMonitoramento.objects.filter(servidor=vinculo).values_list('monitoramento', flat=True)
    manifestacoes = Manifestacao.objects.filter(monitoramento_id__in=monitoramentos_ids).manifestacoes_a_enviar()
    return locals()
