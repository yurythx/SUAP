from django.shortcuts import get_object_or_404
from edu.models.projeto_integrador import ProjetoIntegrador, AtividadeProjetoIntegrador
from django.http import HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from djtools.utils import (
    rtr,
    httprr,
    permission_required,
)

from edu.forms import (
    AvaliarAtividadeProjetoIntegradorForm,
    AvaliarProjetoIntegradorFormFactory,
    AdicionarAlunoProjetoIntegradorForm,
)


@rtr()
@login_required()
def projetointegrador(request, pk):
    obj = get_object_or_404(ProjetoIntegrador, pk=pk)
    if not obj.pode_visualizar(request.user):
        return HttpResponseForbidden()
    title = str(obj)
    matricula_diario = obj.participantes.filter(matricula_periodo__aluno__matricula=request.user.username).first()
    is_professor = obj.is_professor(request.user)
    pode_registrar_atividade = is_professor and not obj.finalizado
    pode_gerenciar = is_professor or obj.diario.can_change(request.user)
    ids_participantes_sem_registro = obj.get_ids_participantes_sem_registro()
    if pode_gerenciar and 'del_participante' in request.GET and not obj.finalizado:
        obj.participantes.remove(request.GET['del_participante'])
        obj.avaliacaoprojetointegrador_set.filter(participante_id=request.GET['del_participante']).delete()
        return httprr(request.path, 'Participante removido com sucesso.')
    if is_professor and 'finalizar' in request.GET:
        finalizar = bool(int(request.GET['finalizar']))
        obj.processar(finalizar)
        msg = 'Encerramento realizado com sucesso.' if finalizar else 'Reabertura realizada com sucesso.'
        return httprr(request.path, msg)
    obj.checar_avaliacoes()
    return locals()


@rtr()
@login_required()
def adicionar_aluno_projetointegrador(request, pk):
    obj = get_object_or_404(ProjetoIntegrador, pk=pk)
    if (not obj.is_professor(request.user) and not obj.diario.can_change(request.user)) or obj.finalizado:
        return HttpResponseForbidden()
    title = 'Adicionar Aluno'
    form = AdicionarAlunoProjetoIntegradorForm(data=request.POST or None, instance=obj)
    if form.is_valid():
        for participante in form.cleaned_data['participantes']:
            obj.participantes.add(participante)
        return httprr(obj.get_absolute_url(), 'Aluno(s) adicionado(s) com sucesso.', close_popup=True)
    return locals()


@rtr()
@permission_required('edu.view_projetointegrador')
def avaliar_atividade_projeto_integrador(request, pk):
    obj = get_object_or_404(AtividadeProjetoIntegrador, pk=pk)
    if not obj.projeto_integrador.pode_gerenciar(request.user):
        return HttpResponseForbidden()
    title = 'Avaliar Atividade'
    form = AvaliarAtividadeProjetoIntegradorForm(data=request.POST or None, instance=obj)
    if form.is_valid():
        form.save()
        return httprr('..', 'Avaliação realizada com sucesso.')
    return locals()


@rtr()
@permission_required('edu.view_projetointegrador')
def avaliar_projeto_integrador(request, pk, etapa):
    obj = get_object_or_404(ProjetoIntegrador, pk=pk)
    if not obj.pode_gerenciar(request.user):
        return HttpResponseForbidden()
    title = 'Avaliar Projeto'
    form = AvaliarProjetoIntegradorFormFactory(data=request.POST or None, instance=obj, files=request.FILES or None, etapa=etapa)
    if form.is_valid():
        erros = form.processar()
        if erros:
            return httprr(obj.get_absolute_url(), 'Alguns registros não foram processados: ' + '; '.join(erros), 'warning', close_popup=True)
        return httprr(obj.get_absolute_url(), 'Avaliação realizada com sucesso.', 'success', close_popup=True)
    return locals()
