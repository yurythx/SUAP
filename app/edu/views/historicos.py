from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404

from djtools import layout
from djtools.utils import (
    group_required,
    httprr,
    permission_required,
    rtr,
)
from edu.forms import (
    GetRegistroHistoricoFormClass,
    ImprimirBoletimAlunoForm,
    ImprimirBoletinsEmLoteForm,
    ImprimirHistoricoFinalEmLoteForm,
    ImprimirHistoricoFinalForm,
    ImprimirHistoricoParcialForm,
)
from edu.models import Aluno, HistoricoEscolarParcial, RegistroEmissaoDiploma, RegistroHistorico


@rtr()
@group_required('Aluno')
@login_required()
def boletim_aluno(request):
    aluno = get_object_or_404(Aluno, matricula=request.user.username)
    return httprr(f'/edu/aluno/{aluno.matricula}/?tab=boletim')


@rtr()
def historico_final_digital(request, pk, codigo):
    title = f'Histórico Final Digital - {codigo}'
    category = 'Ensino'
    icon = 'certificate'
    obj = get_object_or_404(RegistroEmissaoDiploma, pk=pk)
    assinatura_digital = obj.get_assinatura_digital()
    if assinatura_digital and codigo != assinatura_digital.get_codigo_validacao_xml_historico():
        return httprr('/', 'Código inválido.', 'error')
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    return locals()


@rtr()
def historico_parcial_digital(request, pk, codigo):
    title = f'Histórico Parcial Digital - {codigo}'
    category = 'Ensino'
    icon = 'certificate'
    obj = HistoricoEscolarParcial.objects.get(pk=pk)
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    return locals()


@rtr()
@login_required()
@permission_required('edu.efetuar_matricula')
def imprimir_historico(request, tipo):
    if tipo.lower() == 'parcial':
        title = 'Impressão de Histórico Parcial'
        form = ImprimirHistoricoParcialForm(request.POST or None)
    elif tipo.lower() == 'final':
        title = 'Impressão de Histórico Final'
        form = ImprimirHistoricoFinalForm(request.POST or None)

    if form.is_valid():
        return form.processar()
    return locals()


@rtr()
@login_required()
@permission_required('edu.efetuar_matricula')
def imprimir_historico_em_lote(request):
    title = 'Impressão de Histórico Final em Lote'
    form = ImprimirHistoricoFinalEmLoteForm(request.POST or None)

    if form.is_valid():
        alunos = form.processar()
        if alunos.count() > 100 and not request.user.is_superuser:
            return httprr('.', 'A quantidade máxima de impressão de históricos em lote é de 100 alunos por vez.', 'error')

        pks_alunos = '_'.join(str(pk) for pk in alunos.values_list('pk', flat=True))
        return httprr(f'/edu/emitir_historico_final_pdf/{pks_alunos}/')

    return locals()


@rtr()
@login_required()
@permission_required('edu.emitir_boletim')
def imprimir_boletins_alunos_em_lote(request):
    title = 'Impressão de Boletins em Lote'
    form = ImprimirBoletinsEmLoteForm(request.POST or None)

    if form.is_valid():
        alunos = form.processar()
        pks_alunos = '_'.join(str(pk) for pk in alunos.values_list('pk', flat=True))
        param = '?landscape=1' if form.cleaned_data.get('disposicao_texto') == 'paisagem' else ''
        return httprr(f'/edu/emitir_boletim_pdf/{pks_alunos}/{param}')

    return locals()


@rtr()
@login_required()
@permission_required('edu.efetuar_matricula')
def imprimir_boletim_aluno(request):
    title = 'Selecione o Aluno/Período'
    form = ImprimirBoletimAlunoForm(request.POST or None)
    if form.is_valid():
        return form.processar()
    return locals()


@rtr()
@login_required
def adicionar_registro_historico(request, pk):
    title = 'Adicionar registro de histórico acadêmico'
    obj = Aluno.objects.filter(id=pk).first()
    if obj is None:
        return httprr('/', 'Aluno não encontrado.', 'error', close_popup=True)
    if not obj.pode_adicionar_registro_historico(request.user):
        return httprr(
            obj.get_absolute_url(), 'Você não tem permissão para adicionar um registro no histórico deste aluno.', 'error', close_popup=True
        )
    form = GetRegistroHistoricoFormClass(mobilidade_academica=False)(data=request.POST or None, request=request, aluno=obj)
    if form.is_valid():
        form.save()
        return httprr(f'{obj.get_absolute_url()}?tab=historico', 'Dados salvos com sucesso.', close_popup=True)
    return locals()


@rtr()
@login_required
def editar_registro_historico(request, pk):
    title = 'Editar registro de histórico acadêmico'
    obj = RegistroHistorico.objects.filter(id=pk).first()
    if obj is None:
        return httprr('/', 'Registro de histórico acadêmico não encontrado.', 'error', close_popup=True)
    if not obj.matricula_periodo.aluno.pode_editar_registro_historico(request.user):
        return httprr(
            f'{obj.matricula_periodo.aluno.get_absolute_url()}?tab=historico',
            'Você não tem permissão para editar um registro de histórico acadêmico deste aluno.',
            'error',
            close_popup=True,
        )
    form = GetRegistroHistoricoFormClass(mobilidade_academica=False)(
        data=request.POST or None, request=request, instance=obj, aluno=obj.matricula_periodo.aluno
    )
    if form.is_valid():
        form.save()
        return httprr(f'{obj.matricula_periodo.aluno.get_absolute_url()}?tab=historico', 'Registro alterado com sucesso.', close_popup=True)
    return locals()


@rtr()
@login_required
def adicionar_registro_historico_mobilidade_academica(request, pk):
    title = 'Adicionar registro de mobilidade acadêmica'
    obj = Aluno.objects.filter(id=pk).first()
    if obj is None:
        return httprr('/', 'Aluno não encontrado.', 'error', close_popup=True)
    if not obj.pode_gerenciar_mobilidade_academica(request.user):
        return httprr(
            obj.get_absolute_url(), 'Você não tem permissão para adicionar um registro no histórico deste aluno.', 'error', close_popup=True
        )
    form = GetRegistroHistoricoFormClass()(data=request.POST or None, request=request, aluno=obj)
    if form.is_valid():
        form.save()
        return httprr(f'{obj.get_absolute_url()}?tab=historico', 'Dados salvos com sucesso.', close_popup=True)
    return locals()


@rtr()
@login_required
def editar_registro_historico_mobilidade_academica(request, pk):
    title = 'Editar registro de mobilidade acadêmica'
    obj = RegistroHistorico.objects.filter(id=pk).first()
    if obj is None:
        return httprr('/', 'Registro de mobilidade acadêmica não encontrado.', 'error', close_popup=True)
    if not obj.pode_gerenciar_mobilidade_academica(request.user):
        return httprr(
            f'{obj.matricula_periodo.aluno.get_absolute_url()}?tab=historico',
            'Você não tem permissão para editar um registro de mobilidade acadêmica deste aluno.',
            'error',
            close_popup=True,
        )
    form = GetRegistroHistoricoFormClass()(data=request.POST or None, request=request, instance=obj, aluno=obj.matricula_periodo.aluno)
    if form.is_valid():
        form.save()
        return httprr(f'{obj.matricula_periodo.aluno.get_absolute_url()}?tab=historico', 'Registro alterado com sucesso.', close_popup=True)
    return locals()
