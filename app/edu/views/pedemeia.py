from datetime import date
from django.utils.safestring import mark_safe
from django.shortcuts import get_object_or_404

from djtools.utils import httprr, permission_required, rtr
from edu import tasks
from edu.forms import (
    CalcularFrequenciaPeDeMeiaForm,
    OperacaoPeDeMeiaForm,
    ConsultarCodigoSGPForm,
    RelatoInconsistenciaPeDeMeiaForm,
)
from edu.models import Aluno, FrequenciaPeDeMeia, Lote


@rtr()
@permission_required('edu.view_operacaopedemeia')
def lote_pedemeia(request, pk):
    obj = get_object_or_404(Lote.objects, pk=pk)
    title = str(obj.operacao)
    if 'sincronizar' in request.GET:
        obj.sincronizar()
        return httprr(request.path, 'Lote sincronizado com sucesso')
    return locals()


@rtr()
@permission_required('edu.view_operacaopedemeia')
def calcular_frequencia_pedemeia(request):
    title = 'Calcular Frequência'
    form = CalcularFrequenciaPeDeMeiaForm(data=request.POST or None)
    if form.is_valid():
        ano_letivo = form.cleaned_data['ano_letivo']
        periodo_letivo = form.cleaned_data['periodo_letivo']
        mes = form.cleaned_data['mes']
        atualizar_existente = form.cleaned_data['atualizar_existente']
        modalidades = list(form.cleaned_data['modalidades'].values_list('pk', flat=True))
        return tasks.calcular_frequencia_pedemeia(ano_letivo, periodo_letivo, mes, modalidades=modalidades, atualizar_existente=atualizar_existente)
    return locals()


@rtr()
@permission_required('edu.view_operacaopedemeia')
def consultar_codigo_sgp(request):
    title = 'Consultar Código SGP'
    form = ConsultarCodigoSGPForm(data=request.POST or None)
    if form.is_valid():
        matriculas = form.processar()
        if matriculas:
            links = ''.join([f'&nbsp;<a target="_blank" href="/edu/aluno/{matricula}/">{matricula}</a>' for matricula in matriculas.split()])
            return httprr(request.path, mark_safe(f'A matrícula associada ao código informado é {links}'))
        else:
            form.add_error(None, 'Nenhuma matrícula período vinculada a esse código.')
    return locals()


@rtr()
@permission_required('edu.view_operacaopedemeia')
def cadastrar_operacao_pedemeia(request):
    title = 'Cadastrar Operação'
    form = OperacaoPeDeMeiaForm(data=request.POST or None, files=request.FILES or None)
    if form.is_valid():
        operacao = form.processar()
        if operacao:
            return httprr(f'/admin/edu/operacaopedemeia/?id__exact={operacao.pk}', 'Operação cadastrada com sucesso')
        form.add_error(None, 'Nenhum dado encontrado para os parâmetros informados.')
    return locals()


@rtr()
def relatar_inconsistencia_pedemeia(request):
    aluno = get_object_or_404(Aluno.locals, matricula=request.user.username)

    title = 'Relatar Inconsistência'
    form = RelatoInconsistenciaPeDeMeiaForm(data=request.POST or None)
    if form.is_valid():
        form.instance.data = date.today()
        form.instance.aluno = aluno
        form.save()
        return httprr('..', 'Relato cadastrado com sucesso.')
    return locals()


@rtr()
def detalhar_frequencia_pedemeia(request, pk):
    obj = get_object_or_404(FrequenciaPeDeMeia.objects, pk=pk)
    title = f'Detalhamento de Frequência - {obj.mes}/{obj.ano}'
    return locals()
