from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404

from djtools.utils import httprr, permission_required, rtr

from ..forms import AfastamentoForm, HomologarAfastamentoForm
from ..models import AfastamentoPlanejado, PlanejamentoAnual, PlanejamentoMensal


@rtr('auditoria/templates/form.html')
@permission_required('comum.is_auditor')
def cadastrar_afastamento(request, afastamento_id):
    mensal = get_object_or_404(PlanejamentoMensal, pk=afastamento_id)
    planejamento_anual: PlanejamentoAnual = mensal.planejamento_anual
    form = AfastamentoForm(request.POST or None, request.FILES or None, planejamento=mensal)
    target_url = planejamento_anual.get_absolute_url()
    if form.is_valid():
        form.save()
        # Redirecionar ou renderizar com mensagem de sucesso
        return httprr(target_url, 'Afastamento cadastrado com sucesso!', tag='success', close_popup=True)
    return locals()  # Renderizar o template com os dados necessários


@rtr('auditoria/templates/afastamento/form.html')
@permission_required('comum.is_auditor')
def editar_afastamento(request, afastamento_id):
    afastamento: AfastamentoPlanejado = get_object_or_404(AfastamentoPlanejado, pk=afastamento_id)
    title = f'Editar Afastamento - {afastamento}'
    planejamento: PlanejamentoMensal = afastamento.planejamento
    readonly = not afastamento.pode_editar(request.user)
    form = AfastamentoForm(request.POST or None, request.FILES or None, readonly=readonly, instance=afastamento, planejamento=planejamento)
    target_url = planejamento.planejamento_anual.get_absolute_url()
    if form.is_valid():
        form.save()
        return httprr(target_url, 'Afastamento atualizado com sucesso!', close_popup=True, tag='success')

    return locals()


@permission_required('comum.is_auditor')
def remover_afastamento(request, afastamento_id):
    afastamento: AfastamentoPlanejado = get_object_or_404(AfastamentoPlanejado, pk=afastamento_id)
    planejamento: PlanejamentoMensal = afastamento.planejamento
    target_url = planejamento.planejamento_anual.get_absolute_url()
    if not afastamento.pode_remover(request.user):
        return httprr(target_url, 'Remoção não permitida.', close_popup=True, tag='error')
    afastamento.delete()
    return httprr(target_url, 'Afastamento removido com sucesso.', close_popup=True, tag='success')


@rtr('auditoria/templates/afastamento/form.html')
@permission_required('comum.is_auditor')
def avaliar_afastamento(request: HttpRequest, afastamento_id: int) -> HttpResponse | dict:
    afastamento: AfastamentoPlanejado = get_object_or_404(AfastamentoPlanejado, pk=afastamento_id)
    title = 'Homologar Afastamento'
    readonly = not afastamento.pode_homologar(request.user)
    planejamento: PlanejamentoMensal = afastamento.planejamento
    target_url = planejamento.planejamento_anual.get_absolute_url()
    if readonly and request.method == 'POST':
        return httprr(target_url, 'Você não pode avaliar este afastamento.', close_popup=True, tag='error')
    form = HomologarAfastamentoForm(request.POST or None, request.FILES or None, instance=afastamento)
    if form.is_valid():
        form.save()
        return httprr(target_url, 'Afastamento avaliado com sucesso!', close_popup=True, tag='success')
    return locals()
