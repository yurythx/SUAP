from django.core.cache import cache
from django.shortcuts import get_object_or_404

from djtools.utils import (
    httprr,
    permission_required,
    rtr,
)
from edu import tasks
from edu.forms import QuantidadeAlunosForm, SimulacaoAfastamentoForm, SimulacaoCargaHorariaProfessorForm, SimulacaoContratacaoForm, TaxaEvasaoForm
from edu.models import CenarioOferta, PrevisaoQuantidadeAlunos, SimulacaoAfastamento, SimulacaoContratacao


@rtr()
@permission_required('edu.view_cenariooferta')
def cenariooferta(request, pk):
    title = 'Cenário de Oferta'
    obj = get_object_or_404(CenarioOferta, pk=pk)
    if 'del_simulacao_contratacao' in request.GET:
        obj.simulacaocontratacao_set.filter(pk=request.GET['del_simulacao_contratacao']).delete()
        return httprr(request.path, 'Ação realizada com sucesso.')
    if 'del_simulacao_afastamento' in request.GET:
        obj.simulacaoafastamento_set.filter(pk=request.GET['del_simulacao_afastamento']).delete()
        return httprr(request.path, 'Ação realizada com sucesso.')
    if 'reprocessar_variaveis' in request.GET:
        return tasks.cenario_oferta(obj)

    contexto = cache.get(f'edu_cenariooferta_{obj.id}')
    if contexto:
        grupos_atuacao = contexto.get('grupos_atuacao')
        professores = contexto.get('professores')
    else:
        return tasks.cenario_oferta(obj)
    return locals()


@rtr()
@permission_required('edu.add_previsaoquantidadealunos')
def editar_taxa_evasao(request, pk):
    title = 'Taxa de Evasão'
    obj = get_object_or_404(PrevisaoQuantidadeAlunos, pk=pk)
    form = TaxaEvasaoForm(data=request.POST or None, request=request, instance=obj)
    if form.is_valid():
        form.save()
        return httprr('..', 'Ação realizada com sucesso.')
    return locals()


@rtr()
@permission_required('edu.add_previsaoquantidadealunos')
def simular_carga_horaria_professor(request, pk, professor_pk):
    title = 'Carga Horário do Professor'
    obj = get_object_or_404(CenarioOferta, pk=pk)
    instance = obj.simulacaocargahorariaprofessor_set.filter(pk=professor_pk).first()
    form = SimulacaoCargaHorariaProfessorForm(data=request.POST or None, request=request, instance=instance)
    if form.is_valid():
        if form.instance.ch_sala_aula_semanal != form.instance.professor.ch_sala_aula_semanal:
            form.instance.cenario = obj
            form.save()
        else:
            form.instance.delete()
        return httprr('..', 'Ação realizada com sucesso.')
    return locals()


@rtr()
@permission_required('edu.add_previsaoquantidadealunos')
def editar_quantidade_alunos(request, pk):
    title = 'Quantidade de Alunos'
    obj = get_object_or_404(PrevisaoQuantidadeAlunos, pk=pk)
    form = QuantidadeAlunosForm(data=request.POST or None, request=request, instance=obj)
    if form.is_valid():
        form.save()
        return httprr('..', 'Ação realizada com sucesso.')
    return locals()


@rtr()
@permission_required('edu.add_previsaoquantidadealunos')
def adicionar_simulacao_afastamento(request, pk, pk2=None):
    title = 'Simulação de Afastamento'
    obj = get_object_or_404(CenarioOferta, pk=pk)
    instance = get_object_or_404(SimulacaoAfastamento, pk=pk2) if pk2 else None
    form = SimulacaoAfastamentoForm(data=request.POST or None, request=request, instance=instance)
    if form.is_valid():
        form.instance.cenario = obj
        form.save()
        return httprr('..', 'Simulação cadastrada com sucesso.')
    return locals()


@rtr()
@permission_required('edu.add_previsaoquantidadealunos')
def adicionar_simulacao_contratacao(request, pk, pk2=None):
    title = 'Simulação de Afastamento'
    obj = get_object_or_404(CenarioOferta, pk=pk)
    instance = get_object_or_404(SimulacaoContratacao, pk=pk2) if pk2 else None
    form = SimulacaoContratacaoForm(data=request.POST or None, request=request, instance=instance)
    if form.is_valid():
        form.instance.cenario = obj
        form.save()
        return httprr('..', 'Simulação cadastrada com sucesso.')
    return locals()
