from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.template.defaultfilters import pluralize

from djtools import layout
from djtools.utils import group_required, httprr, permission_required, rtr
from solenidades.forms import DeferirAgendamento, EditarAgendamentoSolenidadeForm
from solenidades.models import AgendamentoSolenidade


@layout.atribuidos_a_meus_grupos()
def index_atribuidos_a_meus_grupos(request):
    pendencias = []
    usuario = request.user
    if usuario.has_group_cached('Operador de Gabinete Sistêmico', ignore_groups_if_superuser=False):
        qtd = AgendamentoSolenidade.objects.filter(deferida__isnull=True, cancelada=False).count()
        if qtd:
            pendencias.append(
                {
                    'titulo': f'Solicitaç{pluralize(qtd, "ão,ões")} de agendamento de solenidade',
                    'subtitulo': ' a avaliar',
                    'qtd': qtd,
                    'url': '/admin/solenidades/agendamentosolenidade/',
                }
            )
    return pendencias


@rtr()
@permission_required('solenidades.delete_agendamentosolenidade')
def cancelar_agendamento(request, pk):
    agendamento_solenidade = get_object_or_404(AgendamentoSolenidade, id=pk)
    if agendamento_solenidade.deferida is not None and request.user != agendamento_solenidade.solicitante.user:
        raise PermissionDenied
    agendamento_solenidade.cancelada = True
    agendamento_solenidade.save()
    return httprr('/admin/solenidades/agendamentosolenidade/', 'Operação realizada com sucesso.')


@rtr()
@group_required('Operador de Gabinete Sistêmico')
def editar_agendamento(request, pk):
    title = 'Editar Agendamento de Solenidade'
    agendamento_solenidade = get_object_or_404(AgendamentoSolenidade, id=pk)
    form = EditarAgendamentoSolenidadeForm(request.POST or None, request=request, instance=agendamento_solenidade)
    if form.is_valid():
        form.save()
        return httprr('..', 'Operação realizada com sucesso.')
    return locals()


@rtr()
@group_required('Operador de Gabinete Sistêmico')
def deferir_agendamento(request, pk):
    title = 'Deferir Agendamento de Solenidade'
    agendamento_solenidade = get_object_or_404(AgendamentoSolenidade, id=pk)
    form = DeferirAgendamento(request.POST or None, request=request, instance=agendamento_solenidade)
    if form.is_valid():
        form.save()
        return httprr('..', 'Operação realizada com sucesso.')
    return locals()


@rtr()
@group_required('Operador de Gabinete Sistêmico')
def indeferir_agendamento(request, pk):
    agendamento_solenidade = get_object_or_404(AgendamentoSolenidade, id=pk)
    agendamento_solenidade.deferida = False
    agendamento_solenidade.save()
    agendamento_solenidade.enviar_notificacao_status()
    return httprr('/admin/solenidades/agendamentosolenidade/', 'Operação realizada com sucesso.')


@rtr()
@permission_required('solenidades.view_agendamentosolenidade')
def ver_agendamento(request, pk):
    title = f'Solicitação Agendamento Solenidade {pk}'
    agendamento = get_object_or_404(AgendamentoSolenidade, id=pk)
    calendario = AgendamentoSolenidade.programacao_atual(agendamento)
    eh_operador_gabinete_sistemico = request.user.has_group_cached('Operador de Gabinete Sistêmico', ignore_groups_if_superuser=False)
    return locals()
