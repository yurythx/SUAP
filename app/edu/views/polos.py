import datetime

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404

from comum.models import Ano
from djtools.templatetags.filters import format_
from djtools.utils import (
    XlsResponse,
    documento,
    group_required,
    httprr,
    permission_required,
    rtr,
)
from edu.forms import CoordenadorPoloForm, HorarioAtendimentoPoloForm, TransferirPoloAlunoForm, TutorPoloForm
from edu.models import (
    Aluno,
    AtividadePolo,
    CoordenadorPolo,
    HorarioCoordenadorPolo,
    HorarioFuncionamentoPolo,
    HorarioPolo,
    HorarioTutorPolo,
    PeriodoLetivoAtualPolo,
    Polo,
    TutorPolo,
)
from edu.utils import TabelaAlunoPoloNivelEnsino, TabelaPoloAnoNivelEnsino


@login_required()
@rtr()
def meu_polo(request):
    aluno = get_object_or_404(Aluno, matricula=request.user.username)
    if aluno.polo:
        definiu_horario = aluno.polo.definiu_horario()
        atividades = aluno.polo.get_proximas_atividades().filter(confirmada=True)
        turnos = aluno.polo.get_horarios_por_turno()
        meus_tutores = aluno.polo.get_tutores(aluno.curso_campus)
        coordenador_titular = aluno.polo.get_coordenador_titular()
        return locals()
    else:
        raise PermissionDenied


@permission_required('edu.view_polo')
@rtr()
def polo(request, pk):
    obj = get_object_or_404(Polo.locals, pk=pk)
    atividades = obj.get_proximas_atividades()
    periodo_letivo_atual = PeriodoLetivoAtualPolo.get_instance(request, obj)
    ano_letivo = Ano.objects.get(ano=periodo_letivo_atual.ano)
    periodo_letivo = periodo_letivo_atual.periodo
    turmas = obj.turma_set.filter(ano_letivo=ano_letivo, periodo_letivo=periodo_letivo)
    title = f'{obj}'
    cursos = obj.get_cursos_ofertados()
    usuario_coordenador = obj.coordenadorpolo_set.filter(vinculo=request.user.get_vinculo()).exists()
    tabela_polo_ano_nivel_ensino = TabelaPoloAnoNivelEnsino(obj.aluno_set.all())
    definiu_horario = obj.definiu_horario()
    turnos = obj.get_horarios_por_turno()
    coordenador_titular = obj.get_coordenador_titular()

    coordenadores = obj.coordenadorpolo_set.all()
    tutores = obj.tutorpolo_set.all()

    if request.user.has_perm('edu.change_polo'):
        url = f'/edu/polo/{obj.pk}/?tab=usuarios'
        if 'coordenador_titular_polo_id' in request.GET:
            o = get_object_or_404(CoordenadorPolo, pk=request.GET['coordenador_titular_polo_id'])
            CoordenadorPolo.objects.all().update(titular=False)
            o.titular = True
            o.save()
            return httprr(url, 'Coordenador de Polo Titular definido com sucesso.')

    return locals()


@permission_required('edu.change_polo')
@rtr()
def adicionar_coordenador_polo(request, pk, coordenador_id=None):
    polo = get_object_or_404(Polo, pk=pk)
    title = f'Adicionar responsável: {polo}'
    instance = CoordenadorPolo.objects.get(pk=coordenador_id) if coordenador_id else None
    form = CoordenadorPoloForm(data=request.POST or None, instance=instance, files=request.FILES or None)
    if form.is_valid():
        form.processar(polo)
        return httprr('..', 'Coordenador de Polo adicionado com sucesso.')
    return locals()


@group_required('Administrador Acadêmico, Secretário Acadêmico, Diretor de Avaliação e Regulação do Ensino, Coordenador de Polo EAD Sistêmico')
@rtr()
def adicionar_tutor_polo(request, pk, pk_tutor=None):
    title = 'Adicionar Tutor do Polo'
    polo = get_object_or_404(Polo, pk=pk)
    tutor_polo = pk_tutor and TutorPolo.objects.get(pk=pk_tutor) or None
    form = TutorPoloForm(polo, tutor_polo, request.POST or None)
    if pk_tutor:
        form.fields['vinculo'].initial = tutor_polo.vinculo.pk
        form.fields['cursos'].initial = tutor_polo.cursos.all().values_list('pk', flat=True)
    if form.is_valid():
        form.processar()
        return httprr('..', 'Tutor de Polo adicionado com sucesso.')
    return locals()


@group_required('Administrador Acadêmico, Secretário Acadêmico, Coordenador de Polo EAD, Aluno, Coordenador de Polo EAD Sistêmico')
@rtr('definir_horario_polo.html')
def definir_horario_tutor_polo(request, pk):
    view_ajax = 'definir_horario_tutor_polo_ajax'
    obj = get_object_or_404(TutorPolo, pk=pk)
    definiu_horario = obj.polo.definiu_horario()
    usuario_coordenador = obj.polo.coordenadorpolo_set.filter(vinculo=request.user.get_vinculo()).exists()
    horario = obj.get_horario() or ''
    if horario:
        horario = f'({horario})'

    title = f'Horário do Tutor {horario}'

    if request.method == 'POST':
        return httprr('..', 'Horário definido com sucesso.')

    turnos = obj.get_horarios_por_turno()
    if usuario_coordenador or request.user.has_perm('edu.change_polo'):
        turnos.as_form = True
    else:
        turnos.as_form = False

    return locals()


@permission_required('edu.change_polo')
def definir_horario_tutor_polo_ajax(request, horario_funcionamento_pk, tutor_polo_pk, dia_semana_numero, checked):
    if checked == 'true':
        checked = True
    else:
        checked = False
    horario_funcionamento = get_object_or_404(HorarioFuncionamentoPolo, pk=horario_funcionamento_pk)
    tutor = get_object_or_404(TutorPolo, pk=tutor_polo_pk)
    if not checked:
        HorarioTutorPolo.objects.filter(tutor=tutor, dia_semana=dia_semana_numero, horario_funcionamento=horario_funcionamento).delete()
    else:
        HorarioTutorPolo.objects.create(tutor=tutor, dia_semana=dia_semana_numero, horario_funcionamento=horario_funcionamento)
    return HttpResponse('OK')


@group_required('Administrador Acadêmico, Secretário Acadêmico, Coordenador de Polo EAD, Coordenador de Polo EAD Sistêmico')
@rtr('definir_horario_polo.html')
def definir_horario_coordenador_polo(request, pk):
    view_ajax = 'definir_horario_coordenador_polo_ajax'
    obj = get_object_or_404(CoordenadorPolo, pk=pk)
    definiu_horario = obj.polo.definiu_horario()
    horario = obj.get_horario() or ''
    if horario:
        horario = f'({horario})'

    title = f'Horário do Tutor {horario}'

    if request.method == 'POST':
        return httprr('..', 'Horário definido com sucesso.')

    turnos = obj.get_horarios_por_turno()
    if request.user.has_perm('edu.change_polo'):
        turnos.as_form = True
    else:
        turnos.as_form = False

    return locals()


@permission_required('edu.change_polo')
@rtr()
def definir_horario_polo(request, pk):
    view_ajax = 'definir_horario_polo_ajax'
    obj = get_object_or_404(Polo, pk=pk)
    definiu_horario = obj.definiu_horario()

    title = f'Horário do Polo - {obj}'

    if request.method == 'POST':
        return httprr('..', 'Horário definido com sucesso.')

    turnos = obj.get_horarios_por_turno()
    if request.user.has_perm('edu.change_polo'):
        turnos.as_form = True
    else:
        turnos.as_form = False

    return locals()


@permission_required('edu.change_polo')
def definir_horario_coordenador_polo_ajax(request, horario_funcionamento_pk, coordenador_polo_pk, dia_semana_numero, checked):
    if checked == 'true':
        checked = True
    else:
        checked = False
    horario_funcionamento = get_object_or_404(HorarioFuncionamentoPolo, pk=horario_funcionamento_pk)
    coordenador = get_object_or_404(CoordenadorPolo, pk=coordenador_polo_pk)
    if not checked:
        HorarioCoordenadorPolo.objects.filter(
            coordenador=coordenador, dia_semana=dia_semana_numero, horario_funcionamento=horario_funcionamento
        ).delete()
    else:
        HorarioCoordenadorPolo.objects.create(coordenador=coordenador, dia_semana=dia_semana_numero, horario_funcionamento=horario_funcionamento)
    return HttpResponse('OK')


@permission_required('edu.change_polo')
def definir_horario_polo_ajax(request, horario_funcionamento_pk, polo_pk, dia_semana_numero, checked):
    if checked == 'true':
        checked = True
    else:
        checked = False
    horario_funcionamento = get_object_or_404(HorarioFuncionamentoPolo, pk=horario_funcionamento_pk)
    polo = get_object_or_404(Polo, pk=polo_pk)
    if not checked:
        HorarioPolo.objects.filter(polo=polo, dia_semana=dia_semana_numero, horario_funcionamento=horario_funcionamento).delete()
    else:
        HorarioPolo.objects.create(polo=polo, dia_semana=dia_semana_numero, horario_funcionamento=horario_funcionamento)
    return HttpResponse('OK')


@login_required()
@rtr()
def horario_atendimento_polo(request):
    title = 'Horários de Atendimento dos Polos'
    form = HorarioAtendimentoPoloForm(request.GET or None)
    if form.is_valid():
        polos = form.processar()
        if 'imprimir' in request.GET:
            return horario_atendimento_polo_pdf(request)
        if 'xls' in request.GET:
            rows = []
            for polo in polos:
                if polo.get_horarios_por_turno():
                    rows.append([polo])
                    for turno in polo.get_horarios_por_turno():
                        header = [turno, 'Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']
                        rows.append(header)
                        for horario in turno.horarios:
                            row = [format_(horario)]
                            for dia_semana in horario.dias_semana:
                                row.append(format_(dia_semana['tutores']))
                            rows.append(row)
                rows.append([])
            return XlsResponse(rows)
    return locals()


@documento()
@login_required()
@rtr()
def horario_atendimento_polo_pdf(request):
    title = 'Imprimir Horários de Atendimento dos Polos'
    form = HorarioAtendimentoPoloForm(data=request.GET or None)
    if form.is_valid():
        polos = form.processar()
    uo = request.user.get_vinculo().setor.uo
    return locals()


@rtr()
@permission_required('edu.gerar_relatorio')
def relatorio_ead(request):
    title = 'Relatório EAD'
    tabela_aluno_polo_nivel_ensino = TabelaAlunoPoloNivelEnsino(Aluno.objects.all())
    return locals()


@login_required()
@rtr()
def atividades_polo_aluno(request):
    aluno = get_object_or_404(Aluno, matricula=request.user.username)
    atividades = AtividadePolo.objects.filter(polo=aluno.polo, data_inicio__gte=datetime.datetime.now()).order_by('data_inicio').order_by('data_fim')
    title = f'Próximas Atividades do Polo - {aluno.polo}'
    return locals()


@login_required()
@rtr()
def atividades_polo_tutor(request):
    polos = Polo.objects.filter(tutorpolo__vinculo__user__username=request.user.username)
    atividades = AtividadePolo.objects.filter(polo__in=polos, data_inicio__gte=datetime.datetime.now()).order_by('data_inicio').order_by('data_fim')
    title = 'Próximas Atividades dos Polos'
    return locals()


@rtr()
@permission_required('edu.efetuar_matricula')
@login_required()
def transferir_polo_aluno(request):
    title = 'Alterar Polo de Aluno'
    form = TransferirPoloAlunoForm(request.POST or None)
    if form.is_valid():
        form.processar()
        return httprr('/edu/transferir_polo_aluno/', 'Polo do(s) aluno(s) transferido(s) com sucesso.')
    return locals()
