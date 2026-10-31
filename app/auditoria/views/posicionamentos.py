from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.template.defaultfilters import slugify

from auditoria.forms.posicionamento import SolicitarRevisaoPosicionamentoForm
from auditoria.models.monitoramento import Monitoramento
from djtools.utils import httprr, permission_required, rtr

from ..forms import PosicionamentoForm, PosicionamentoFormFactory, RevisaoPosicionamentoForm
from ..models import Manifestacao, Posicionamento, RevisaoPosicionamento


@rtr('auditoria/templates/posicionamento/posicionamento.html')
@login_required()
def visualizar_posicionamento(request, posicionamento_id):
    posicionamento: Posicionamento = get_object_or_404(Posicionamento, id=posicionamento_id)
    title = f'Posicionamento #{posicionamento.id}'
    eh_auditor = request.user.has_perm('comum.is_auditor') and request.user.has_group_cached(['Auditor'])
    if not posicionamento.pode_visualizar(request.user):
        return httprr('..', 'Você não tem permissão para realizar essa ação.', tag='error')
    posicionamento.notificar_acesso_auditado(request.user)
    return locals()


@rtr('auditoria/templates/posicionamento/form.html')
@permission_required('comum.is_auditor')
def adicionar_posicionamento(request, manifestacao_id):
    manifestacao: Manifestacao = get_object_or_404(Manifestacao, id=manifestacao_id)
    target_url = manifestacao.get_absolute_url()
    title = 'Adicionar posicionamento'
    if not manifestacao.pode_adicionar_posicionamento(request.user):
        return httprr(target_url, 'Você não tem permissão para realizar essa ação.', tag='error')
    #
    form = PosicionamentoFormFactory(request=request, manifestacao=manifestacao)
    if form.is_valid():
        instance: Posicionamento = form.save()
        return httprr(instance.get_absolute_url(), 'Posicionamento registrado com sucesso')
    return locals()


@rtr('auditoria/templates/posicionamento/form.html')
@permission_required('comum.is_auditor')
def editar_posicionamento(request, posicionamento_id):
    title = f'Editar posicionamento #{posicionamento_id}'
    posicionamento: Posicionamento = get_object_or_404(Posicionamento, id=posicionamento_id)
    target_url = posicionamento.get_absolute_url()
    if not posicionamento.pode_editar(request.user):
        return httprr(target_url, 'Você não tem permissão para realizar essa ação.', tag='error')
    form = PosicionamentoForm(request.POST or None, request=request, instance=posicionamento)
    if form.is_valid():
        form.save()
        return httprr(target_url, 'Posicionamento registrado com sucesso')
    return locals()


@permission_required('comum.is_auditor')
def remover_posicionamento(request, posicionamento_id):
    posicionamento: Posicionamento = get_object_or_404(Posicionamento, id=posicionamento_id)
    target_url = '..'
    if not posicionamento.pode_editar(request.user):
        return httprr(target_url, 'Você não tem permissão para realizar essa ação.', tag='error')
    posicionamento.delete()
    return httprr(target_url, 'Posicionamento removido com sucesso')


@rtr('auditoria/templates/form.html')
@permission_required('comum.is_auditor')
def solicitar_revisao_posicionamento(request, posicionamento_id):
    posicionamento: Posicionamento = get_object_or_404(Posicionamento, id=posicionamento_id)
    target_url = posicionamento.get_absolute_url()
    title = 'Solicitar Revisao de Posicionamento'
    if not posicionamento.pode_solicitar_revisao(request.user):
        return httprr(target_url, 'Você não tem permissão para realizar essa ação.', tag='error')
    form = SolicitarRevisaoPosicionamentoForm(request.POST or None, posicionamento=posicionamento)
    if form.is_valid():
        form.processar()
        return httprr(target_url, 'Solicitação enviada com sucesso')
    return locals()


@permission_required('comum.is_auditor')
def publicar_posicionamento(request, posicionamento_id):
    posicionamento: Posicionamento = get_object_or_404(Posicionamento, id=posicionamento_id)
    monitoramento: Monitoramento = posicionamento.referencia
    tab = slugify(monitoramento.unidade)
    target_url = f'{monitoramento.recomendacao.get_absolute_url()}?tab={tab}'
    if not posicionamento.pode_publicar(request.user):
        return httprr(target_url, 'Você não tem permissão para realizar essa ação.', tag='error')
    #
    with transaction.atomic():
        posicionamento.publicar(request.user)
        posicionamento.save()
        return httprr(target_url, 'Posicionamento publicado com sucesso.')


@rtr('auditoria/templates/posicionamento/form.html')
@permission_required('comum.is_auditor')
def adicionar_revisao_posicionamento(request, posicionamento_id):
    posicionamento: Posicionamento = get_object_or_404(Posicionamento, id=posicionamento_id)
    target_url = posicionamento.get_absolute_url()
    if not posicionamento.pode_revisar(request.user):
        return httprr(target_url, 'Você não tem permissão para realizar essa ação.', tag='error')
    form = RevisaoPosicionamentoForm(request.POST or None, request=request, posicionamento=posicionamento)
    if form.is_valid():
        form.save()
        return httprr(target_url, 'Revisão adicionada.')
    return locals()


@rtr('auditoria/templates/posicionamento/form.html')
@permission_required('comum.is_auditor')
def editar_revisao_posicionamento(request, revisao_id):
    revisao: RevisaoPosicionamento = get_object_or_404(RevisaoPosicionamento, id=revisao_id)
    target_url = '..'
    if not revisao.pode_enviar(request.user):
        return httprr(target_url, 'Você não tem permissão para realizar essa ação.', tag='error')
    form = RevisaoPosicionamentoForm(request.POST or None, request=request, instance=revisao)
    if form.is_valid():
        form.save()
        return httprr(target_url, 'Revisão editada com sucesso.')
    return locals()


@rtr()
@permission_required('comum.is_auditor')
def remover_revisao_posicionamento(request, revisao_id):
    revisao: RevisaoPosicionamento = get_object_or_404(RevisaoPosicionamento, id=revisao_id)
    target_url = revisao.posicionamento.get_absolute_url()
    if not revisao.pode_remover(request.user):
        return httprr(target_url, 'Você não tem permissão para realizar essa ação.', tag='error')
    revisao.delete()
    return httprr(target_url, 'Revisão removida com sucesso.')


@permission_required('comum.is_auditor')
def enviar_revisao_posicionamento(request, revisao_id):
    revisao: RevisaoPosicionamento = get_object_or_404(RevisaoPosicionamento, id=revisao_id)
    target_url = '..'
    if not revisao.pode_enviar(request.user):
        return httprr(target_url, 'Você não tem permissão para realizar essa ação.', tag='error')
    #
    with transaction.atomic():
        revisao.enviar()
        revisao.save()
        return httprr(target_url, 'Revisão encaminhada com sucesso.')
