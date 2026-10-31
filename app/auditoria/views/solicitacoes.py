from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404

from auditoria.models.monitoramento import Monitoramento
from djtools.utils import httprr, permission_required, rtr

from ..forms import CancelarSolicitacaoProvidenciaForm
from ..models import SolicitacaoProvidencia


@rtr('auditoria/templates/solicitacoes/providencias.html')
@login_required()
def visualizar_solicitacao_providencia(request, solicitacao_id):
    solicitacao = get_object_or_404(SolicitacaoProvidencia, pk=solicitacao_id)
    title = f'Solicitação de Providência #{solicitacao.id}'
    return locals()


@rtr()
@permission_required('comum.is_auditor')
def cancelar_solicitacao_providencia(request, solicitacao_id):
    solicitacao = get_object_or_404(SolicitacaoProvidencia, pk=solicitacao_id)
    title = f'Cancelar Solicitação de Providência #{solicitacao.id}'
    if not solicitacao.pode_cancelar(request.user):
        return httprr('..', 'Você não possui permissão para cancelar essa solicitação.', tag='error')
    form = CancelarSolicitacaoProvidenciaForm(request.POST or None, request=request, instance=solicitacao)
    if form.is_valid():
        form.save()
        return httprr('..', 'Solicitação de providência cancelada com sucesso.')
    return locals()


@rtr()
@permission_required('comum.is_auditor')
def remover_solicitacao_providencia(request, solicitacao_id):
    solicitacao = get_object_or_404(SolicitacaoProvidencia, pk=solicitacao_id)
    if not solicitacao.pode_remover(request.user):
        return httprr('.', 'Você não possui permissão para remover essa solicitação.', tag='error')

    monitoramento: Monitoramento = solicitacao.monitoramento
    monitoramento.ultima_solicitacao = (
        SolicitacaoProvidencia.objects.filter(monitoramento=monitoramento).exclude(pk=solicitacao.pk).order_by('-id').first()
    )
    monitoramento.save()
    solicitacao.delete()
    return httprr('.', 'Solicitação de providência removida com sucesso.')
