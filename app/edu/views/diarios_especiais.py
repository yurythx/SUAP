from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404

from djtools.utils import (
    documento,
    httprr,
    permission_required,
    rtr,
)
from edu import perms
from edu.forms import (
    AdicionarAlunosDiarioEspecialForm,
    AdicionarAlunosDiarioEspecialWizard,
    AdicionarEncontroDiarioEspecialForm,
    AdicionarProfessorDiarioEspecialForm,
    AtualizarEncontroDiarioEspecialForm,
    DefinirLocalAulaDiarioEspecialForm,
)
from edu.models import Aluno, ConfiguracaoCreditosEspeciais, DiarioEspecial, Encontro, HorarioAula, HorarioAulaDiarioEspecial, Matriz, Professor


@rtr()
@login_required()
def diarioespecial(request, pk):
    obj = get_object_or_404(DiarioEspecial, pk=pk)
    title = f'{obj.pk} - {obj.componente.descricao}'
    is_usuario_professor = obj.professores.filter(vinculo__user=request.user).exists()
    pode_realizar_procedimentos = (
        request.user.has_perm('edu.change_diario') or request.user.has_perm('edu.change_diarioespecial')
    ) and perms.realizar_procedimentos_diarios_especiais(request.user, obj)

    ids_alunos_encontros = obj.encontro_set.values_list('participantes', flat=True).distinct()

    if 'alunos_pk' in request.POST and (is_usuario_professor or pode_realizar_procedimentos):
        for aluno_pk in request.POST.getlist('alunos_pk'):
            if int(aluno_pk) not in ids_alunos_encontros:
                aluno = Aluno.objects.get(pk=aluno_pk)
                obj.participantes.remove(aluno)
        obj.save()

    if 'del_encontro' in request.GET and (is_usuario_professor or pode_realizar_procedimentos):
        obj.encontro_set.filter(pk=request.GET['del_encontro']).delete()
        return httprr(request.META.get('HTTP_REFERER', '.'), 'Encontro removido com sucesso.')

    if 'del_professor' in request.GET and (is_usuario_professor or pode_realizar_procedimentos):
        professor = Professor.objects.get(pk=request.GET['del_professor'])
        obj.professores.remove(professor)
        obj.save()
        return httprr(request.META.get('HTTP_REFERER', '.'), 'Professor removido com sucesso.')

    return locals()


@permission_required('edu.change_diarioespecial')
@rtr()
def definir_local_aula_diario_especial(request, diario_especial_pk):
    title = 'Definir Local de Aula'
    diario_especial = get_object_or_404(DiarioEspecial, pk=diario_especial_pk)

    pode_realizar_procedimentos = perms.realizar_procedimentos_diarios_especiais(request.user, diario_especial)
    if not pode_realizar_procedimentos:
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    sala_id = None
    if diario_especial.sala:
        sala_id = diario_especial.sala_id
    form = DefinirLocalAulaDiarioEspecialForm(diario_especial, data=request.POST or None, initial={'sala': sala_id})
    if form.is_valid():
        form.processar()
        return httprr('..', 'Local definido com sucesso.')
    return locals()


@login_required()
def definir_horario_aula_diario_especial_ajax(request, diario_especial_pk, horario_aula_pk, dia_semana_numero, checked):
    if checked == 'true':
        checked = True
    else:
        checked = False
    diario_especial = get_object_or_404(DiarioEspecial, pk=diario_especial_pk)

    pode_realizar_procedimentos = perms.realizar_procedimentos_diarios_especiais(request.user, diario_especial)
    if not pode_realizar_procedimentos:
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    horario_aula = get_object_or_404(HorarioAula, pk=horario_aula_pk)
    if not checked:
        HorarioAulaDiarioEspecial.objects.filter(diario_especial=diario_especial, dia_semana=dia_semana_numero, horario_aula=horario_aula).delete()
    else:
        HorarioAulaDiarioEspecial.objects.create(diario_especial=diario_especial, dia_semana=dia_semana_numero, horario_aula=horario_aula)
    return HttpResponse('OK')


@permission_required('edu.change_diarioespecial')
@rtr()
def definir_horario_aula_diario_especial(request: HttpRequest, diario_especial_pk: int) -> HttpResponse:
    obj = get_object_or_404(DiarioEspecial, pk=diario_especial_pk)

    pode_realizar_procedimentos = perms.realizar_procedimentos_diarios_especiais(request.user, obj)
    if not pode_realizar_procedimentos:
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    campus_definiu_horario = (obj.horario_campus_id and obj.horario_campus.horarioaula_set.exists()) or HorarioAula.objects.filter(
        horario_campus__uo=obj.diretoria.setor.uo
    ).exists()

    horario_aula = obj.get_horario_aulas() or ''
    if horario_aula:
        horario_aula = f'({horario_aula})'

    title = f'Definir Horário de Aula {horario_aula}'

    if request.method == 'POST':
        return httprr('..', 'Horário definido com sucesso.')

    turnos = obj.get_horarios_aula_por_turno()
    turnos.as_form = True

    return locals()


@login_required
@rtr()
def adicionar_aluno_diario_especial(request, diario_especial_pk):
    diario_especial = get_object_or_404(DiarioEspecial, pk=diario_especial_pk)
    title = 'Adicionar Alunos na Atividade Pedagógica Específica'
    form = AdicionarAlunosDiarioEspecialForm(diario_especial, data=request.POST or None)

    is_usuario_professor = diario_especial.professores.filter(vinculo__user=request.user).exists()
    pode_realizar_procedimentos = (
        request.user.has_perm('edu.change_diario') or request.user.has_perm('edu.change_diarioespecial')
    ) and perms.realizar_procedimentos_diarios_especiais(request.user, diario_especial)

    if not is_usuario_professor and not pode_realizar_procedimentos:
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    if form.is_valid():
        form.processar()
        return httprr('..', 'Alunos adicionados com sucesso.')

    return locals()


@login_required
@rtr()
def adicionar_alunos_diario_especial(request, diario_especial_pk):
    diario_especial = get_object_or_404(DiarioEspecial, pk=diario_especial_pk)
    title = 'Adicionar Alunos na Atividade Pedagógica Específica'
    data = 'diario' in request.GET and request.GET or None
    form = AdicionarAlunosDiarioEspecialWizard(request, diario_especial, data=data)

    is_usuario_professor = request.user.is_authenticated and diario_especial.professores.filter(vinculo__user=request.user).exists()
    pode_realizar_procedimentos = (
        request.user.has_perm('edu.change_diario') or request.user.has_perm('edu.change_diarioespecial')
    ) and perms.realizar_procedimentos_diarios_especiais(request.user, diario_especial)

    if not is_usuario_professor and not pode_realizar_procedimentos:
        return httprr('/', 'Você não tem permissão para realizar isso.', 'error')

    if form.is_valid():
        form.processar()
        return httprr(f'/edu/diarioespecial/{diario_especial.pk}/?tab=participantes', 'Alunos adicionados com sucesso.')

    return locals()


@permission_required('edu.change_diarioespecial')
@rtr()
def adicionar_professor_diario_especial(request, diario_especial_pk):
    diario_especial = get_object_or_404(DiarioEspecial, pk=diario_especial_pk)
    title = 'Adicionar Professor na Atividade Pedagógica Específica'
    form = AdicionarProfessorDiarioEspecialForm(diario_especial, data=request.POST or None)

    pode_realizar_procedimentos = perms.realizar_procedimentos_diarios_especiais(request.user, diario_especial)
    if not pode_realizar_procedimentos:
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    if form.is_valid():
        form.processar()
        return httprr('..', 'Professor adicionado com sucesso.')

    return locals()


@permission_required('edu.cadastrar_encontro_diarioespecial')
@rtr()
def adicionar_encontro_diario_especial(request, diario_especial_pk):
    diario_especial = get_object_or_404(DiarioEspecial, pk=diario_especial_pk)
    title = 'Adicionar Encontro na Atividade Pedagógica Específica'
    form = AdicionarEncontroDiarioEspecialForm(diario_especial, data=request.POST or None)

    if form.is_valid():
        form.processar()
        return httprr('..', 'Encontro adicionado com sucesso.')

    return locals()


@login_required
@documento()
@rtr()
def frequencia_diarioespecial(request, pk):
    obj = get_object_or_404(Encontro, pk=pk)
    uo = obj.diario_especial.diretoria.setor.uo
    return locals()


@permission_required('edu.cadastrar_encontro_diarioespecial')
@rtr()
def atualizar_encontro_diario_especial(request, pk):
    obj = get_object_or_404(Encontro, pk=pk)
    title = 'Atualizar Encontro na Atividade Pedagógica Específica'
    form = AtualizarEncontroDiarioEspecialForm(instance=obj, data=request.POST or None)
    if form.is_valid():
        form.save()
        return httprr('..', 'Encontro atualizado com sucesso.')

    return locals()


@rtr()
@permission_required('edu.view_configuracaocreditosespeciais')
def configuracaocreditosespeciais(request, pk):
    obj = get_object_or_404(ConfiguracaoCreditosEspeciais, pk=pk)
    title = 'Configuração de Créditos Especiais'
    if 'desvincular_matriz' in request.GET and request.user.has_perm('edu.change_configuracaocreditosespeciais'):
        matriz = Matriz.objects.get(pk=request.GET.get('desvincular_matriz'))
        matriz.configuracao_creditos_especiais = None
        matriz.save()
        return httprr(f'/edu/configuracaoatividadecomplementar/{pk}/?tab=matrizes', 'Matriz desvinculada com sucesso.')
    return locals()
