from django.contrib.auth.decorators import login_required
from django.http.response import HttpResponseForbidden
from django.shortcuts import get_object_or_404

from djtools import layout
from djtools.utils import (
    documento,
    httprr,
    rtr,
)
from edu.forms import AlterarCoordenadorPlanoEnsinoForm, AvaliarPlanoEstudoForm, DefinirPlanoEstudoForm, DevolverPlanoEnsino, PlanoEnsinoPublicForm
from edu.models import PlanoEnsino, PlanoEstudo


@rtr()
def planoensino_public(request):
    title = 'Planos de Ensino'
    category = 'Ensino'
    icon = 'file'
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    form = PlanoEnsinoPublicForm(data=request.GET or None)
    planos = PlanoEnsino.objects.none()
    if form.is_valid():
        planos = form.processar()
    return locals()


@documento()
@rtr()
def plano_ensino_pdf(request, pk):
    obj = get_object_or_404(PlanoEnsino, pk=pk)
    return locals()


@login_required()
@rtr()
def alterar_coordenador_plano_ensino(request, pk):
    title = 'Alterar Coordenador de Curso'
    obj = get_object_or_404(PlanoEnsino, pk=pk, diario__turma__curso_campus__diretoria__setor__uo=request.user.get_vinculo().setor.uo)
    form = AlterarCoordenadorPlanoEnsinoForm(data=request.POST or None, instance=obj)
    if form.is_valid():
        form.save()
        return httprr('..', 'Ação realizada com sucesso.')
    return locals()


@login_required()
@rtr()
def devolver_plano_ensino(request, destino, pks):
    title = 'Devolver Plano de Ensino'
    form = DevolverPlanoEnsino(data=request.POST or None)
    if form.is_valid():
        for plano in PlanoEnsino.objects.filter(pk__in=pks.split('__')):
            if destino == 'professor' and request.user.has_group_cached('Coordenador de Curso'):
                plano.devolver_para_professor(request.user, form.cleaned_data['justificativa'])
            elif destino == 'coordenador' and request.user.has_group_cached('Diretor Acadêmico'):
                plano.devolver_para_coordenador(request.user, form.cleaned_data['justificativa'])
        return httprr('..', 'Ação realizada com sucesso.')
    return locals()


@login_required()
@rtr()
def planoestudo(request, pk):
    obj = get_object_or_404(PlanoEstudo, pk=pk)
    resumo_ch = obj.get_resumo_ch()
    return locals()


@login_required()
@rtr()
def definir_planoestudo(request, pk):
    title = 'Definir Plano de Estudo'
    obj = get_object_or_404(PlanoEstudo, pk=pk)
    is_coordenador = obj.pedido_matricula.matricula_periodo.aluno.curso_campus.coordenador == request.user.get_vinculo()
    form = DefinirPlanoEstudoForm(data=request.POST or None, plano_estudo=obj)
    if form.is_valid():
        form.processar()
        return httprr('..', 'Plano de estudo definido com sucesso.')
    return locals()


@login_required
@documento()
@rtr()
def planoestudo_pdf(request, pk):
    obj = get_object_or_404(PlanoEstudo, pk=pk)
    return locals()


@login_required()
@rtr()
def avaliar_plano_estudo(request, pks):
    title = 'Devolver Plano de Ensino'
    qs = PlanoEstudo.objects.filter(pk__in=pks.split('__'))
    if not request.user.has_group_cached('Diretor Acadêmico') and not request.user.is_superuser:
        return HttpResponseForbidden()
    form = AvaliarPlanoEstudoForm(data=request.POST or None)
    if form.is_valid():
        form.processar(qs)
        return httprr('..', 'Ação realizada com sucesso.')
    return locals()
