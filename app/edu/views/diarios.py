import datetime
import math
from typing import Any

import pandas as pd
from django.apps import apps
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, Subquery
from django.db.models.aggregates import Max, Min, Sum, Variance
from django.http import HttpRequest, HttpResponse
from django.http.response import HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.utils.safestring import mark_safe
from sentry_sdk import capture_exception

from comum.models import Ano, APIExterna, Configuracao, Sala
from comum.utils import get_uo
from djtools.html.calendarios import Calendario, CalendarioPlus
from djtools.templatetags.filters import format_
from djtools.utils import (
    JsonResponse,
    getattrr,
    group_required,
    httprr,
    normalizar_nome_proprio,
    permission_required,
    retira_caracteres_ocultos,
    rtr,
    running_tests,
    send_mail,
    send_notification,
)
from edu import perms, tasks
from edu.forms import (
    AbonoFaltasLoteForm,
    AdicionarAlunosDiarioForm,
    AgendarAvaliacaoForm,
    AlterarNotaForm,
    AulaForm,
    AvaliadorEquivalenciaComponenteForm,
    AvaliarAbonoFaltasForm,
    AvaliarEquivalenciaComponenteForm,
    ConfigurarAmbienteVirtualDiarioForm,
    DefinirLocalAulaForm,
    DividirDiarioForm,
    EncerrarSuspensaoDiarioForm,
    EntregaEtapaForm,
    EntregaTrabalhoForm,
    FrequenciaPraticaProfissionalForm,
    ImportarMaterialAulaForm,
    ImportarXMLTimeTables,
    ListarDiarioMatriculaAlunoForm,
    ListarDiariosVinculoAlunoForm,
    MateriaisAulaForm,
    ObservacaoDiarioForm,
    OcorrenciaDiarioForm,
    ProfessorDiarioForm,
    ReservarSalaAulaFormFactory,
    RespostaDiscussaoForm,
    SelecionarHorarioCampusExportarXMLTimeTables,
    SolicitarProrrogacaoEtapaForm,
    SolicitarRelancamentoEtapaForm,
    SuspensaoDiarioForm,
    TopicoDiscussaoForm,
    TrabalhoForm,
    TransferirDiarioForm,
    VincularMaterialAulaForm,
)
from edu.models import (
    AbonoFaltas,
    Aluno,
    Aula,
    AvaliadorEquivalenciaComponente,
    Componente,
    ConfiguracaoAvaliacao,
    CursoCampus,
    Diario,
    EquivalenciaComponente,
    EstruturaCurso,
    Falta,
    HorarioAula,
    HorarioAulaDiario,
    ItemConfiguracaoAvaliacao,
    MaterialAula,
    MaterialDiario,
    MatriculaDiario,
    MatriculaPeriodo,
    NotaAvaliacao,
    OcorrenciaDiario,
    PedidoMatriculaDiario,
    PeriodoLetivoAtual,
    Professor,
    ProfessorDiario,
    SituacaoMatriculaPeriodo,
    SolicitacaoProrrogacaoEtapa,
    SolicitacaoRelancamentoEtapa,
    SolicitacaoReposicaoAtividade,
    SuspensaoDiario,
    TopicoDiscussao,
    Trabalho,
    Turma,
)
from edu.models.diarios import ObservacaoDiario
from rh.models import Servidor, UnidadeOrganizacional


@group_required('Administrador Acadêmico, Diretor Acadêmico, Coordenador de Curso, Coordenador de Modalidade Acadêmica, Secretário Acadêmico')
@rtr('transferir_turma_ou_diario.html')
def transferir_diario(request, diario_origem, matriculas_diario):
    diario_origem = get_object_or_404(Diario.locals, pk=diario_origem)
    matriculas_diario = matriculas_diario.split('_')

    aluno_com_nota = False
    matriculas = diario_origem.matriculadiario_set.filter(pk__in=matriculas_diario, situacao__in=[MatriculaDiario.SITUACAO_CURSANDO])

    if not matriculas:
        return httprr(
            f'/edu/diario/{diario_origem.pk}/?tab=notas_faltas', 'Só é possível realizar a transferência de alunos com situação cursando.', 'error'
        )

    for matricula in matriculas:
        if matricula.tem_nota_lancada():
            aluno_com_nota = True
            break
    if aluno_com_nota:
        return httprr(
            f'/edu/diario/{diario_origem.pk}/?tab=notas_faltas', 'Só é possível realizar a transferência de alunos sem nota lançada.', 'error'
        )

    title = 'Transferência de Diário'
    form = TransferirDiarioForm(diario_origem, data=request.POST or None)

    diario_destino = form.get_entered_data('diario_destino')

    diarios = []
    if diario_destino:
        diarios.append((diario_origem, diario_destino))

    turma_origem = diario_origem.turma
    turma_destino = diario_destino and diario_destino.turma or None

    if form.is_valid():
        diario_origem.transferir(matriculas_diario, diario_destino)
        return httprr(f'/edu/diario/{diario_origem.pk}/', 'Transferência realizada com sucesso.')
    return locals()


@permission_required('edu.change_diario')
@rtr()
def reservar_sala_aula(request, pk):
    title = 'Reservar Sala de Aula'
    manager = request.user.has_group_cached('Diretor Acadêmico') and Diario.objects or Diario.locals
    obj = get_object_or_404(manager, pk=pk)
    pode_reservar_sala = obj.is_reserva_sala_habilitada() and obj.can_change(request.user)
    if not pode_reservar_sala:
        return httprr(f'{obj.get_absolute_url()}?tab=dados_gerais', 'Você não tem permissão para isso.', 'error', close_popup=True)
    Form = ReservarSalaAulaFormFactory(request, pk)
    if request.method == 'POST':
        form = Form(data=request.POST)
        if form.is_valid():
            try:
                form.save()
                return httprr(f'{obj.get_absolute_url()}', 'Salas reservadas com sucesso.', close_popup=True)
            except ValidationError as ex:
                msg_erro = ex
    else:
        form = Form()
    return locals()


@permission_required('edu.change_diario')
@rtr()
def cancelar_reservas_sala_aula(request, pk):
    manager = request.user.has_group_cached('Diretor Acadêmico') and Diario.objects or Diario.locals
    obj = get_object_or_404(manager, pk=pk)
    pode_reservar_sala = obj.is_reserva_sala_habilitada() and obj.can_change(request.user)
    if not pode_reservar_sala:
        return httprr(f'{obj.get_absolute_url()}?tab=dados_gerais', 'Você não tem permissão para isso.', 'error', close_popup=True)
    obj.cancelar_reservas_de_sala()
    return httprr(
        f'{obj.get_absolute_url()}?tab=dados_gerais',
        'Reservas canceladas com sucesso.',
    )


@permission_required('edu.view_diario')
@rtr()
def suspender_diario(request, pk):
    obj = get_object_or_404(Diario.locals, pk=pk)
    title = f'Suspender Diário - {obj}'
    form = SuspensaoDiarioForm(data=request.POST or None)
    if obj.possui_suspensao_aberta():
        return httprr(
            f'{obj.get_absolute_url()}?tab=ocorrencias',
            'Finalize a suspensão que se encontra em aberto na aba "ocorrências".',
            'error',
            close_popup=True,
        )
    if form.is_valid():
        form.instance.diario = obj
        form.save()
        professores_vinculados = [professordiario.professor.vinculo for professordiario in obj.get_professores()]
        texto = (
            f'<h2>Suspensão do Diário {obj}</h2>'
            f'<p>A suspensão  será iniciada em {obj.get_suspensao_vigente().inicio.strftime("%d/%m/%Y")}.</p>'
            f"<p class='more-info'>Para mais informações, acesse: <a href='{obj.get_absolute_url()}?tab=ocorrencias'>{obj}/</a></p>"
        )
        send_notification('[SUAP] Suspensão de Diário', texto, settings.DEFAULT_FROM_EMAIL, professores_vinculados, fail_silently=True)
        return httprr(f'{obj.get_absolute_url()}?tab=ocorrencias', 'Suspensão cadastrada com sucesso.', close_popup=True)
    return locals()


@permission_required('edu.view_diario')
@rtr()
def suspender_diarios_lote(request, pks):
    title = 'Suspender Diários em Lote'
    diarios = Diario.objects.filter(pk__in=pks.split('_'))

    form = SuspensaoDiarioForm(data=request.POST or None)
    if form.is_valid():
        qtd_suspensos = 0
        inicio = form.cleaned_data['inicio']
        justificativa = form.cleaned_data['justificativa']
        motivo = form.cleaned_data.get('motivo', None)
        if len(diarios) > 15:
            return tasks.suspender_diarios_lote(diarios, inicio, justificativa, motivo)

        for obj in diarios:
            obj.suspender(inicio, justificativa, motivo)
            qtd_suspensos += 1
        return httprr('..', f'{qtd_suspensos} suspensões cadastradas com sucesso.')
    return locals()


@permission_required('edu.view_diario')
@rtr()
def encerrar_suspensao_diario(request, pk):
    obj = get_object_or_404(SuspensaoDiario.objects, pk=pk)
    title = f'Encerrar Suspensão de Diário - {obj}'
    if not obj.diario.possui_suspensao_aberta():
        return httprr('..', 'Este diário não está com suspensão vigente".', 'error', close_popup=True)

    form = EncerrarSuspensaoDiarioForm(data=request.POST or None, instance=obj)
    if form.is_valid():
        form.save()
        professores_vinculados = [professordiario.professor.vinculo for professordiario in obj.diario.get_professores()]
        texto = (
            f'<h2>Encerramento de Suspensão do Diário {obj.diario}</h2>'
            f'<p>A suspensão  será encerrada em {obj.fim.strftime("%d/%m/%Y")}.</p>'
            f"<p class='more-info'>Para mais informações, acesse: <a href='{obj.diario.get_absolute_url()}?tab=ocorrencias'>{obj.diario}/</a></p>"
        )
        send_notification(
            '[SUAP] Encerramento de Suspensão de Diário', texto, settings.DEFAULT_FROM_EMAIL, professores_vinculados, fail_silently=True
        )
        return httprr(f'{obj.diario.get_absolute_url()}?tab=ocorrencias', 'Suspensão encerrada com sucesso.', close_popup=True)
    return locals()


@permission_required('edu.view_diario')
@rtr()
def encerrar_suspensao_diarios_lote(request, pks):
    title = 'Encerrar Suspensão de Diário em Lote'
    diarios = Diario.objects.filter(pk__in=pks.split('_'))

    form = EncerrarSuspensaoDiarioForm(data=request.POST or None)
    if form.is_valid():
        qtd_encerrados = 0
        fim = form.cleaned_data['fim']
        if len(diarios) > 15:
            return tasks.encerrar_suspensao_diarios_lote(diarios, fim)

        for obj in diarios:
            if obj.possui_suspensao_aberta():
                qtd_encerrados += 1
            obj.encerrar_suspensao(fim)

        return httprr('..', f'{qtd_encerrados} suspensões de Diários encerradas com sucesso.')
    return locals()


@permission_required('edu.change_diario')
def remover_suspensao_diario(request, pk):
    obj = get_object_or_404(SuspensaoDiario.objects, pk=pk)
    title = f'Encerrar Suspensão de Diário - {obj}'
    if obj.diario.estah_suspenso():
        return httprr('..', 'Não pode ser removida pois o diário está suspenso.', 'error', close_popup=True)

    if obj.fim is None or obj.fim > datetime.date.today():
        obj.delete()
        return httprr(f'{obj.diario.get_absolute_url()}?tab=ocorrencias', 'Suspensão removida com sucesso.', close_popup=True)
    return locals()


@permission_required('edu.view_diario')
@rtr()
def diario(request, pk, polo_pk=None):
    NOTA_DECIMAL = settings.NOTA_DECIMAL
    CASA_DECIMAL = settings.CASA_DECIMAL
    MULTIPLICADOR_DECIMAL = NOTA_DECIMAL and CASA_DECIMAL == 1 and 10 or 100
    MATRICULADO = SituacaoMatriculaPeriodo.MATRICULADO

    manager = Diario.objects if request.user.has_group_cached('Diretor Acadêmico') else Diario.locals
    obj = get_object_or_404(manager.select_related('componente_curricular__componente_curricular_associado'), pk=pk)
    title = f'Diário ({obj.pk}) - {obj.componente_curricular.componente.sigla}'

    if not obj.is_aberto() and obj.matriculadiario_set.filter(situacao=MatriculaDiario.SITUACAO_CURSANDO).exists():
        obj.abrir()

    pode_realizar_procedimentos = obj.can_change(request.user)
    pode_reservar_sala = pode_realizar_procedimentos and obj.is_reserva_sala_habilitada()
    pode_gerenciar_posse = pode_realizar_procedimentos and request.user.has_perm('edu.mudar_posse_diario') and obj.is_aberto()
    pode_gerenciar_professor = pode_realizar_procedimentos and request.user.has_perm('edu.add_professordiario') and obj.is_aberto()
    pode_manipular_etapa_1 = pode_realizar_procedimentos and obj.em_posse_do_registro(1)
    pode_manipular_etapa_2 = pode_realizar_procedimentos and obj.em_posse_do_registro(2)
    pode_manipular_etapa_3 = pode_realizar_procedimentos and obj.em_posse_do_registro(3)
    pode_manipular_etapa_4 = pode_realizar_procedimentos and obj.em_posse_do_registro(4)
    pode_manipular_etapa_5 = pode_realizar_procedimentos and obj.em_posse_do_registro(5)

    etapa = 5
    materiais_diario = MaterialDiario.objects.filter(professor_diario__diario=obj).order_by('-data_vinculacao', 'material_aula__descricao')
    quantidade_vagas_estourada = obj.matriculadiario_set.filter(situacao=MatriculaDiario.SITUACAO_CURSANDO).count() > obj.quantidade_vagas
    ch_presencial = obj.get_carga_horaria_presencial()
    qtd_avaliacoes = obj.componente_curricular.qtd_avaliacoes

    if 'moodle' in request.GET and obj.integracao_com_moodle:
        moodle = APIExterna.MOODLE.get_service()
        if not APIExterna.MOODLE.ativo:
            return httprr('.', 'A integração com o Moodle não está ativa temporariamente, tente mais tarde.', 'error')
        try:
            acao = request.GET['moodle']
            if acao == 'sincronizar':
                url = moodle.sincronizar(obj)
                obj.url_moodle = url
                obj.save()
                return httprr('.', f'Dados enviados com sucesso! A URL de acesso para o ambiente virtual é: {url}')
            elif acao == 'importar_notas':
                try:
                    contador = moodle.importar_notas(obj, request)
                except ValidationError as e:
                    return httprr('.', f'Ocorreu um erro ao importar notas do Moodle: {e.message}', tag='error')
                return httprr('.', f'Total de {contador} nota(s) importad(a) com sucesso!')
        except Exception as e:
            capture_exception(e)
            return httprr('.', f'Erro ao se comunicar com o Moodle: {e}', tag='error')

    if request.GET.get('xls'):
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename=diario_{pk}.xlsx'

        rows_agrupada = []
        cabecalho = ['#', 'Matrícula', 'Nome', 'T. Faltas', '%Freq', 'Situação']
        for avaliacao in range(1, obj.componente_curricular.qtd_avaliacoes + 1):
            cabecalho.append(f'Nota Etapa {avaliacao}')
            cabecalho.append(f'Falta Etapa {avaliacao}')
        cabecalho += ['MD', 'Nota Etapa Final', 'MFD/Conceito']

        # Data for first sheet
        data_sheet1 = []
        count = 0
        for matricula_diario in obj.matriculadiario_set.all():
            count += 1
            row = [
                format_(count),
                format_(matricula_diario.matricula_periodo.aluno.matricula),
                format_(normalizar_nome_proprio(matricula_diario.matricula_periodo.aluno.get_nome_social_composto())),
                format_(matricula_diario.get_numero_faltas()),
                format_(matricula_diario.get_percentual_carga_horaria_frequentada()),
                format_(matricula_diario.get_situacao_diario()['rotulo']),
            ]
            if matricula_diario.diario.componente_curricular.qtd_avaliacoes > 0:
                row.append(format_(matricula_diario.get_nota_boletim(1)))
                row.append(format_(matricula_diario.get_numero_faltas_primeira_etapa()))
            if matricula_diario.diario.componente_curricular.qtd_avaliacoes > 1:
                row.append(format_(matricula_diario.get_nota_boletim(2)))
                row.append(format_(matricula_diario.get_numero_faltas_segunda_etapa()))
            if matricula_diario.diario.componente_curricular.qtd_avaliacoes > 2:
                row.append(format_(matricula_diario.get_nota_boletim(3)))
                row.append(format_(matricula_diario.get_numero_faltas_terceira_etapa()))
            if matricula_diario.diario.componente_curricular.qtd_avaliacoes > 3:
                row.append(format_(matricula_diario.get_nota_boletim(4)))
                row.append(format_(matricula_diario.get_numero_faltas_quarta_etapa()))
            if matricula_diario.diario.componente_curricular.qtd_avaliacoes > 0:
                row.append(format_(matricula_diario.get_media_disciplina_boletim()))
                row.append(format_(matricula_diario.get_nota_boletim(5)))
                row.append(format_(matricula_diario.get_media_final_disciplina_boletim()))
            data_sheet1.append(row)

        df1 = pd.DataFrame(data_sheet1, columns=cabecalho)

        # Data for second sheet
        cabecalho_sheet2 = ['#', 'Etapa', 'Qtd.', 'Data', 'Professor', 'Conteúdo']
        data_sheet2 = []
        count = 0
        for aula in obj.get_aulas():
            count += 1
            row = [
                format_(count),
                format_(aula.etapa),
                format_(aula.quantidade),
                format_(aula.data),
                format_(str(aula.professor_diario.professor)),
                format_(retira_caracteres_ocultos(aula.conteudo)),
            ]
            data_sheet2.append(row)

        df2 = pd.DataFrame(data_sheet2, columns=cabecalho_sheet2)

        with pd.ExcelWriter(response, engine='openpyxl') as writer:
            df1.to_excel(writer, sheet_name='Dados gerais', index=False)
            df2.to_excel(writer, sheet_name='Registros de Aulas', index=False)

        return response

    if request.method == 'POST' and request.user.has_perm('edu.add_professordiario'):
        if 'lancamento_nota' in request.POST:
            if running_tests():
                try:
                    obj.processar_notas(request.POST)
                    return httprr('.', 'Notas registradas com sucesso.')
                except Exception as e:
                    return httprr('..', str(e), 'error', anchor='etapa')

    if not obj.turma.curso_campus.diretoria.ead:
        horarios_com_choque = obj.get_horarios_com_choque()

    tab = request.GET.get('tab', '')

    if tab == 'estatisticas':
        estatisticas = get_estatisticas_diario(obj)

    elif tab in ['', 'dados_gerais']:
        plano_disciplina = obj.componente_curricular.get_plano_disciplina_ppc()
        plano_disciplina_pomc = obj.componente_curricular.get_plano_disciplina_pomc(obj.turma.curso_campus)

    elif tab == 'notas_faltas':
        polos = obj.get_polos()
        if polo_pk is None:
            polo_pk = polos and polos.first().pk or None
        else:
            polo_pk = int(polo_pk)
        matriculas_diario_por_polo = obj.get_matriculas_diario_por_polo(polo_pk)

    exibir_todos_alunos = not obj.matriculadiario_set.filter(situacao=MatriculaDiario.SITUACAO_CURSANDO).exists()
    return locals()


def get_estatisticas_diario(obj):
    estatisticas = {}
    estatisticas['alunos_aprovados'] = MatriculaDiario.objects.filter(diario=obj, situacao=MatriculaDiario.SITUACAO_APROVADO).count()
    estatisticas['alunos_reprovados'] = MatriculaDiario.objects.filter(diario=obj, situacao=MatriculaDiario.SITUACAO_REPROVADO).count()
    estatisticas['alunos_prova_final'] = MatriculaDiario.objects.filter(diario=obj, situacao=MatriculaDiario.SITUACAO_PROVA_FINAL).count()
    estatisticas['alunos_tcdt'] = MatriculaDiario.objects.filter(
        diario=obj,
        situacao__in=[
            MatriculaDiario.SITUACAO_TRANCADO,
            MatriculaDiario.SITUACAO_CANCELADO,
            MatriculaDiario.SITUACAO_DISPENSADO,
            MatriculaDiario.SITUACAO_TRANSFERIDO,
        ],
    ).count()
    estatisticas['alunos_pendentes'] = MatriculaDiario.objects.filter(diario=obj, situacao=MatriculaDiario.SITUACAO_PENDENTE).count()
    estatisticas['alunos_reprovados_por_falta'] = len(
        [
            matricula_diario
            for matricula_diario in obj.matriculadiario_set.all()
            if matricula_diario.get_situacao_diario()['rotulo'] == 'Reprov. por Falta'
        ]
    )
    estatisticas['alunos_aprovados_reprovados_modulo'] = MatriculaDiario.objects.filter(
        diario=obj, situacao=MatriculaDiario.SITUACAO_APROVADO_REPROVADO_MODULO
    ).count()
    if obj.componente_curricular.qtd_avaliacoes > 0:
        nomes_etapa = list(range(1, obj.componente_curricular.qtd_avaliacoes + 1))
        etapas_estatistica = []
        for nome_etapa in nomes_etapa:
            search_field = f'nota_{nome_etapa}'
            pks = (
                NotaAvaliacao.objects.filter(
                    nota__isnull=False, matricula_diario__diario=obj, item_configuracao_avaliacao__configuracao_avaliacao__etapa=nome_etapa
                )
                .values_list('matricula_diario', flat=True)
                .order_by('matricula_diario')
                .distinct()
            )
            matriculas_consideradas = MatriculaDiario.objects.filter(pk__in=pks)
            variancia = matriculas_consideradas.aggregate(Variance(search_field))[f'{search_field}__variance']
            etapa_estatistica = {
                'nome': nome_etapa,
                'media': obj.get_media_notas_by_etapa(nome_etapa),
                'desvio': variancia and math.sqrt(variancia) or variancia,
                'maior_nota': matriculas_consideradas.aggregate(Max(search_field))[f'{search_field}__max'],
                'menor_nota': matriculas_consideradas.aggregate(Min(search_field))[f'{search_field}__min'],
            }
            etapas_estatistica.append(etapa_estatistica)

        estatisticas['etapas_estatistica'] = etapas_estatistica

        valores = []
        for matricula_diario in obj.matriculadiario_set.all():
            mfd = matricula_diario.get_media_final_disciplina()
            if mfd is not None:
                valores.append(mfd)

        if valores:
            media_mfd = sum(valores) / float(len(valores))
            desvio_mfd = math.sqrt(sum((media_mfd - value) ** 2 for value in valores) / len(valores))
            menor_mfd = min(valores)
            maior_mfd = max(valores)
        else:
            media_mfd, desvio_mfd, menor_mfd, maior_mfd = None, None, None, None

        estatisticas['media_mfd'] = media_mfd
        estatisticas['desvio_mfd'] = desvio_mfd
        estatisticas['menor_mfd'] = menor_mfd
        estatisticas['maior_mfd'] = maior_mfd
    return estatisticas


@permission_required('edu.change_diario')
@rtr()
def gerar_configuracoes_avaliacao(request, pk):
    diario = get_object_or_404(Diario.locals, pk=pk)

    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, diario.turma.curso_campus)
    if not pode_realizar_procedimentos:
        return httprr(diario.get_absolute_url(), 'Você não tem permissão para realizar isso.', 'error')

    if not diario.possui_configuracao_avaliacao_inconsistente():
        return httprr(diario.get_absolute_url(), 'Não existe configuração de avaliação inconsistente.', 'error')

    diario.gerar_configuracoes_avaliacao()

    return httprr(diario.get_absolute_url(), 'Configurações de avaliação geradas com sucesso.')


@permission_required('edu.change_diario')
@rtr()
def replicar_diario(request, pk):
    diario = get_object_or_404(Diario.locals, pk=pk)

    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, diario.turma.curso_campus)
    if not pode_realizar_procedimentos:
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    novo_diario = diario.replicar()

    return httprr(novo_diario.get_absolute_url(), 'Diário replicado com sucesso.')


@permission_required('edu.change_diario')
@rtr()
def dividir_diario(request, pk):
    diario = get_object_or_404(Diario.locals, pk=pk)

    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, diario.turma.curso_campus)
    if not pode_realizar_procedimentos:
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    novo_diario = diario.dividir()

    return httprr(
        '..', mark_safe(f'Diário dividido com sucesso. Código do novo diário: <a href="{novo_diario.get_absolute_url()}">{novo_diario.pk}</a>.')
    )


@permission_required('edu.change_diario')
@rtr()
def dividir_diario_individualizado(request, pk):
    diario = get_object_or_404(Diario.locals, pk=pk)
    title = f'Dividir diário - {diario}'

    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, diario.turma.curso_campus)
    if not pode_realizar_procedimentos:
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')
    ids = (
        NotaAvaliacao.objects.filter(matricula_diario__diario=diario, nota__isnull=False)
        .values_list('matricula_diario', flat=True)
        .order_by('matricula_diario')
        .distinct()
    )
    qs = diario.matriculadiario_set.exclude(id__in=ids)
    form = DividirDiarioForm(qs, request.POST or None)
    if form.is_valid():
        novo_diario = diario.dividir(matriculas_diario=form.cleaned_data['matriculas_diario'])
        return httprr(
            '..', mark_safe(f'Diário dividido com sucesso. Código do novo diário: <a href="{novo_diario.get_absolute_url()}">{novo_diario.pk}</a>.')
        )
    return locals()


@permission_required('edu.change_diario')
@rtr()
def dividir_diario_reprovados_dependentes(request, pk):
    diario = get_object_or_404(Diario.locals, pk=pk)

    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, diario.turma.curso_campus)
    if not pode_realizar_procedimentos:
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    novo_diario = diario.dividir_reprovados_dependentes()

    return httprr(
        '..', mark_safe(f'Diário dividido com sucesso. Código do novo diário: <a href="{novo_diario.get_absolute_url()}">{novo_diario.pk}</a>.')
    )


@permission_required('edu.add_professordiario')
@rtr()
def definir_local_aula_diario(request, diario_pk):
    title = 'Definir Local de Aula'
    diario = get_object_or_404(Diario.locals, pk=diario_pk)

    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, diario.turma.curso_campus)
    if not pode_realizar_procedimentos or diario.tem_sala_reservada():
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    form = DefinirLocalAulaForm(diario, data=request.POST or None)
    if form.is_valid():
        form.processar()
        return httprr('..', 'Local definido com sucesso.')
    return locals()


@permission_required('edu.change_diario')
@rtr()
def transferir_posse_diario(request, diario_pk, etapa, destino):
    diario = get_object_or_404(Diario.locals, pk=diario_pk)

    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, diario.turma.curso_campus)
    if not pode_realizar_procedimentos:
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    destino = int(destino)
    etapa = int(etapa)
    if etapa == 1:
        diario.posse_etapa_1 = destino
    elif etapa == 2:
        diario.posse_etapa_2 = destino
    elif etapa == 3:
        diario.posse_etapa_3 = destino
    elif etapa == 4:
        diario.posse_etapa_4 = destino
    elif etapa == 5:
        diario.posse_etapa_5 = destino
    diario.save()
    for matricula_diario in diario.matriculadiario_set.all():
        matricula_diario.registrar_nota_etapa(etapa)
    return httprr(f'/edu/diario/{diario.pk:d}/', 'Posse transferida com sucesso.')


@transaction.atomic
@login_required()
def registrar_chamada_ajax(request, matricula_diario_pk, aula_pk, quantidade):
    aula = get_object_or_404(Aula, pk=aula_pk)
    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, aula.professor_diario.diario.turma.curso_campus)

    if not pode_realizar_procedimentos and not aula.pode_registrar_chamada(request.user):
        return HttpResponse('Você não tem permissão para realizar isso.')

    matricula_diario = MatriculaDiario.objects.filter(pk=matricula_diario_pk, diario_id=aula.professor_diario.diario_id).first()
    if matricula_diario is None:
        return HttpResponse('O aluno não faz parte deste diário. Por favor recarregue a página.')

    qs_falta = Falta.objects.filter(matricula_diario_id=matricula_diario_pk, aula_id=aula_pk)

    if not quantidade:
        qs_falta.delete()
    else:
        falta = qs_falta.first()
        if falta is None:
            falta = Falta()
            falta.aula = aula
            falta.matricula_diario = matricula_diario
        falta.quantidade = quantidade
        falta.abono_faltas = AbonoFaltas.objects.filter(
            deferido=True, aluno_id=matricula_diario.matricula_periodo.aluno_id, data_inicio__lte=aula.data, data_fim__gte=aula.data
        ).first()
        if falta.abono_faltas:
            falta.contabilizar = not falta.abono_faltas.deve_abonar_faltas()
        try:
            falta.save()
        except IntegrityError:
            return HttpResponse('Ocorreu um erro ao salvar o registro de falta. Por favor recarregue a página.')
    return HttpResponse(matricula_diario.get_numero_faltas())


@transaction.atomic
@permission_required('edu.view_diario')
@rtr()
def registrar_chamada(request, diario_pk, etapa=0, matricula_diario_pk=0):
    title = 'Registro de aula/falta'
    inicio_confirmacao_frequencia = Configuracao.get_valor_por_chave('edu', 'inicio_confirmacao_frequencia')

    diario = get_object_or_404(Diario.locals, pk=diario_pk)
    possui_professor = diario.professordiario_set.exists()
    if not possui_professor:
        return httprr(f'/edu/diario/{diario.pk}/', 'Não é possível registrar as aulas pois o professor do diário ainda não foi definido.', 'error')

    is_proprio_professor = diario.professordiario_set.filter(professor__vinculo__user_id=request.user.id).exists()

    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, diario.turma.curso_campus)
    if not pode_realizar_procedimentos and not is_proprio_professor and not request.user.has_group_cached('Pedagogo, Apoio Acadêmico, Membro ETEP'):
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    if 'registro_frequencia_confirmado' in request.GET:
        Aula.objects.filter(professor_diario__diario=diario).filter(pk=request.GET['registro_frequencia_confirmado']).update(
            registro_frequencia_confirmado=True
        )
        return httprr(request.path, 'Registro de frequência confirmado com sucesso.')

    uo = get_uo()
    acesso_total = True if is_proprio_professor or uo == diario.horario_campus.uo else request.user.has_group_cached('Administrador Acadêmico')
    pode_manipular_etapa = diario.is_aberto() and (diario.em_posse_do_registro(etapa) or is_proprio_professor)

    data_atual = datetime.date.today()
    aulas = diario.get_aulas().all()
    etapa = int(etapa)
    if not etapa or etapa == 1:
        aulas = diario.get_aulas_etapa_1().all()
    elif etapa == 2:
        aulas = diario.get_aulas_etapa_2().all()
    elif etapa == 3:
        aulas = diario.get_aulas_etapa_3().all()
    elif etapa == 4:
        aulas = diario.get_aulas_etapa_4().all()
    elif etapa == 5:
        aulas = diario.get_aulas_etapa_5().all()

    if request.POST:
        return httprr('..', 'Faltas registradas com sucesso.')

    polos = diario.get_polos()
    boxes_matriculas = []
    for matriculas in diario.get_matriculas_diario_por_polo():
        if matricula_diario_pk:
            matriculas = matriculas.filter(id=matricula_diario_pk)
        for matricula_diario in matriculas:
            matricula_diario.set_faltas(aulas)
        boxes_matriculas.append(matriculas)

    aulas = diario.get_aulas(etapa)
    qtd_aulas_passadas = 0
    for aula in aulas:
        if aula.data <= data_atual:
            qtd_aulas_passadas += 1

    return locals()


@permission_required('edu.add_professordiario')
@rtr()
def definir_horario_aula_diario(request, diario_pk):
    obj = get_object_or_404(Diario.locals.select_related('componente_curricular__componente_curricular_associado'), pk=diario_pk)

    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, obj.turma.curso_campus)
    if not pode_realizar_procedimentos or obj.tem_sala_reservada():
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    campus_definiu_horario = HorarioAula.objects.filter(horario_campus__uo=obj.turma.curso_campus.diretoria.setor.uo).exists()

    horario_aula = obj.get_horario_aulas() or ''
    if horario_aula:
        horario_aula = f'({horario_aula})'

    title = f'Definir Horário de Aula {horario_aula}'

    if request.method == 'POST':
        qs_pedidos_matricula_nao_processados = PedidoMatriculaDiario.objects.filter(diario=obj, data_processamento__isnull=True)
        if not request.user.has_group_cached('Administrador Acadêmico') and qs_pedidos_matricula_nao_processados.exists():
            return httprr('..', 'Não é possível alterar o horário do diário, pois existem pedidos de matrícula ainda não processados.', 'error')
        else:
            HorarioAulaDiario.objects.filter(diario=obj).delete()
            horarios = dict(request.POST).get('horario')
            if horarios:
                for horario in horarios:
                    horario_split = horario.split(';')
                    horario_aula = get_object_or_404(HorarioAula, pk=horario_split[0])
                    dia_semana = horario_split[1]
                    HorarioAulaDiario.objects.create(diario=obj, dia_semana=dia_semana, horario_aula=horario_aula)
            horarios_com_choque = obj.get_horarios_com_choque(verificar_apenas_existencia=True)
            if horarios_com_choque:
                return httprr(
                    '..', 'Horário definido com sucesso, porém existem alunos deste diário com conflitos de horário com outro(s) diário(s).', 'error'
                )
            else:
                return httprr('..', 'Horário definido com sucesso.')

    turnos = obj.get_horarios_aula_por_turno()
    turnos.as_form = True

    return locals()


@permission_required('edu.add_professordiario')
@rtr()
def adicionar_professor_diario(request, diario_pk, professordiario_pk=None):
    diario = get_object_or_404(Diario.locals, pk=diario_pk)
    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, diario.turma.curso_campus)
    if not pode_realizar_procedimentos:
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')
    professor_diario = None
    if professordiario_pk:
        professor_diario = get_object_or_404(ProfessorDiario, pk=professordiario_pk)
    title = professor_diario and f'{professor_diario}' or 'Adicionar Professor'
    form = ProfessorDiarioForm(diario, data=request.POST or None, instance=professordiario_pk and professor_diario or None, request=request)
    if form.is_valid():
        form.save()
        if professor_diario:
            emails = [professor_diario.professor.vinculo.email_notificacao]
            mensagem = f"""
            Caro(a) Professor(a),

            Informamos que houve uma alteração do seu vínculo no diário {diario} que pode afetar o seu Plano/Relatório Individual de Trabalho de {diario.ano_letivo.ano}.{diario.periodo_letivo}.
            """

            send_mail(f'[SUAP] Alteração de Vínculo - Diário {diario}', mensagem, settings.DEFAULT_FROM_EMAIL, emails, fail_silently=True)
        return httprr('..', 'Professor adicionado/atualizado com sucesso.')
    return locals()


@permission_required('edu.lancar_nota_diario')
@rtr()
def alterar_nota_diario(request, matriculadiario_pk, etapa=0):
    title = 'Alterar Nota'
    matricula_diario = get_object_or_404(MatriculaDiario.locals, id=matriculadiario_pk)
    etapa = int(etapa)
    if etapa == 1:
        nota = matricula_diario.nota_1
    elif etapa == 2:
        nota = matricula_diario.nota_2
    elif etapa == 3:
        nota = matricula_diario.nota_3
    elif etapa == 4:
        nota = matricula_diario.nota_4
    else:
        nota = matricula_diario.nota_final
    form = AlterarNotaForm(data=request.POST or None, initial={'nota': nota})
    if form.is_valid():
        nota = form.cleaned_data['nota']
        if etapa == 1:
            matricula_diario.nota_1 = nota
        elif etapa == 2:
            matricula_diario.nota_2 = nota
        elif etapa == 3:
            matricula_diario.nota_3 = nota
        elif etapa == 4:
            matricula_diario.nota_4 = nota
        else:
            matricula_diario.nota_final = nota
        matricula_diario.save()
        return httprr('..', 'Nota alterada com sucesso')
    return locals()


@permission_required('edu.add_aula')
@rtr()
def adicionar_aula_diario(request, diario_pk, etapa, aula_pk=None):
    diario = get_object_or_404(Diario.locals, pk=diario_pk)
    if aula_pk:
        aula = get_object_or_404(Aula, pk=aula_pk)
    title = '{} Aula'.format(aula_pk and aula and 'Editar' or 'Adicionar')

    form = AulaForm(diario, etapa, data=request.POST or None, instance=aula_pk and aula or None, request=request)
    qtd_etapas = diario.componente_curricular.qtd_avaliacoes

    if form.is_valid():
        obj = form.save(False)
        obj.save()
        outros_professor_diario = form.cleaned_data.get('outros_professor_diario')
        if outros_professor_diario:
            obj.outros_professor_diario.set(outros_professor_diario)
        else:
            obj.outros_professor_diario.clear()
        return httprr('..', 'Aula cadastrada/atualizada com sucesso.', anchor='etapa')
    return locals()


@rtr()
@login_required()
def horario_professor(request, pk, pk_diario):
    pd = get_object_or_404(
        ProfessorDiario, professor_id=pk, diario_id=pk_diario, diario__matriculadiario__matricula_periodo__aluno__matricula=request.user.username
    )
    obj = pd.professor
    diario = pd.diario
    turnos = obj.get_horarios_aula_por_turno(diario.ano_letivo.ano, diario.periodo_letivo)
    return locals()


@rtr()
@login_required()
def meus_diarios(request, diarios=None):
    professor = get_object_or_404(Professor, vinculo__user=request.user)
    if diarios:
        try:
            professores_diario = ProfessorDiario.objects.filter(professor__vinculo__user=request.user, ativo=True, diario__id__in=diarios.split('_'))
        except Exception:
            return httprr('..', 'Diários inválidos.', 'error')
        title = f'Meus Diários Pendentes ({len(professores_diario)})'
    else:
        periodo_letivo_atual = PeriodoLetivoAtual.get_instance(request, professor)
        professores_diario = ProfessorDiario.objects.filter(professor__vinculo__user=request.user, ativo=True)
        professores_diario_anual = professores_diario.filter(
            diario__turma__curso_campus__periodicidade=CursoCampus.PERIODICIDADE_ANUAL, diario__ano_letivo__ano=periodo_letivo_atual.ano
        )

        # excluíndo os diários semestrais em cursos anuais
        if periodo_letivo_atual.periodo == 1:
            professores_diario_anual = professores_diario_anual.exclude(diario__segundo_semestre=True)
        else:
            professores_diario_anual = professores_diario_anual.exclude(
                diario__segundo_semestre=False, diario__componente_curricular__qtd_avaliacoes=2
            )

        professores_diario_semestral = professores_diario.filter(
            diario__turma__curso_campus__periodicidade__in=[CursoCampus.PERIODICIDADE_SEMESTRAL, CursoCampus.PERIODICIDADE_LIVRE],
            diario__ano_letivo__ano=periodo_letivo_atual.ano,
            diario__periodo_letivo=periodo_letivo_atual.periodo,
        )
        professores_diario = (professores_diario_anual | professores_diario_semestral).order_by(
            'diario__turma__curso_campus', 'diario__turma', 'diario'
        )
        diarios_especiais = professor.diarioespecial_set.filter(ano_letivo__ano=periodo_letivo_atual.ano, periodo_letivo=periodo_letivo_atual.periodo)
        qtd_diarios = professores_diario.count() + diarios_especiais.count()
        title = f'Meus Diários ({qtd_diarios})'
    return locals()


@rtr()
@login_required()
def configuracao_avaliacao(request, pk):
    obj = get_object_or_404(ConfiguracaoAvaliacao, pk=pk)
    if (
        not request.user.has_group_cached(
            'Administrador Acadêmico,Diretor Acadêmico,Coordenador de Curso, Coordenador de Modalidade Acadêmica,Secretário Acadêmico,Pedagogo,Coordenador de Polo EAD, Visualizador de Informações Acadêmicas, Auditor,Apoio Acadêmico,Membro ETEP'
        )
        and not obj.diario.professordiario_set.filter(professor__vinculo__user=request.user).exists()
    ):
        return httprr('/', 'Você não tem permissão para acessar essa página.', 'error')
    title = obj.__str__()
    is_lancamento_conceito = obj.diario.is_lancamento_conceito()
    return locals()


@rtr()
@login_required()
def configurar_ambiente_virtual_diario(request, pk):
    title = 'Configurar Ambiente Virtual'
    obj = get_object_or_404(Diario.locals, pk=pk)
    form = ConfigurarAmbienteVirtualDiarioForm(data=request.POST or None, instance=obj)
    if form.is_valid():
        form.save()
        return httprr('..', 'Configuração realizada com sucesso')
    return locals()


@rtr()
@login_required()
def cadastrar_frequencia_pratica_profisional(request, pk, registro_id=None):
    title = 'Frequência de Prática Profissional'
    obj = get_object_or_404(Diario.locals, pk=pk)
    instance = obj.get_frequencias_pratica_profissional().get(pk=registro_id) if registro_id else None
    form = FrequenciaPraticaProfissionalForm(request.POST or None, instance=instance)
    form.fields['matricula_diario'].queryset = obj.matriculadiario_set.all()
    if form.is_valid():
        form.save()
        return httprr('..', 'Cadastro realizado com sucesso.')
    return locals()


@rtr()
@login_required()
def meu_diario(request, diario_pk, etapa=0, polo_pk=None):
    NOTA_DECIMAL = settings.NOTA_DECIMAL
    CASA_DECIMAL = settings.CASA_DECIMAL
    MULTIPLICADOR_DECIMAL = NOTA_DECIMAL and CASA_DECIMAL == 1 and 10 or 100

    obj = get_object_or_404(Diario.locals.select_related('componente_curricular__componente_curricular_associado'), pk=diario_pk)
    if not obj.is_aberto() and obj.matriculadiario_set.filter(situacao=MatriculaDiario.SITUACAO_CURSANDO).exists():
        obj.abrir()

    pode_gerenciar_aula = obj.is_aberto() and request.user.has_perm('edu.add_falta')

    inicio_confirmacao_frequencia = Configuracao.get_valor_por_chave('edu', 'inicio_confirmacao_frequencia')

    plano_disciplina = obj.componente_curricular.get_plano_disciplina_ppc()
    plano_ensino = obj.planoensino_set.first()

    solicitacoes_lab_fisico = None
    solicitacoes_lab_virtual = None
    labfisico_installed = 'labfisico' in settings.INSTALLED_APPS
    labvirtual_installed = 'labvirtual' in settings.INSTALLED_APPS
    if labfisico_installed:
        SolicitacaoLabFisico = apps.get_model('labfisico', 'SolicitacaoLabFisico')
        solicitacoes_lab_fisico = SolicitacaoLabFisico.objects.filter(diario=obj)

    if labvirtual_installed:
        SolicitacaoLabVirtual = apps.get_model('labvirtual', 'SolicitacaoLabVirtual')
        solicitacoes_lab_virtual = SolicitacaoLabVirtual.objects.filter(diario=obj)

    if 'moodle' in request.GET and obj.integracao_com_moodle:
        moodle = APIExterna.MOODLE.get_service()
        if not APIExterna.MOODLE.ativo:
            return httprr('.', 'A integração com o Moodle não está ativa temporariamente, tente mais tarde.', 'error')
        try:
            acao = request.GET['moodle']
            if acao == 'sincronizar':
                url = moodle.sincronizar(obj)
                obj.url_moodle = url
                obj.save()
                return httprr('.', f'Dados enviados com sucesso! A URL de acesso para o ambiente virtual é: {url}')
            elif acao == 'importar_notas':
                try:
                    contador = moodle.importar_notas(obj, request)
                except ValidationError as e:
                    return httprr('.', f'Ocorreu um erro ao importar notas do Moodle: {e.message}', tag='error')
                return httprr('.', f'Total de {contador} nota(s) importad(a) com sucesso!')
        except Exception as e:
            capture_exception(e)
            return httprr('.', 'Erro ao se comunicar com o Moodle. Tente realizar esse procedimento mais tarde.', tag='error')

    if 'registro_frequencia_confirmado' in request.GET:
        pk = int(request.GET['registro_frequencia_confirmado'])
        if pk:
            Aula.objects.filter(professor_diario__diario=obj).filter(pk=pk).update(registro_frequencia_confirmado=True)
        else:
            Aula.objects.filter(professor_diario__diario=obj).filter(data__lte=datetime.date.today()).update(registro_frequencia_confirmado=True)
        return httprr(request.path, 'Registro de frequência confirmado com sucesso.')

    etapa = int(etapa)
    if etapa == 0:
        return httprr(f'/edu/meu_diario/{obj.pk}/{obj.get_num_etapa_posse_professor()}/')
    if etapa > 5 or etapa < 1:
        return httprr('/edu/meus_diarios/', 'Escolha uma Etapa Válida', 'error')
    etapa_str = obj.get_label_etapa(etapa)
    descricao_etapa = f'Etapa {etapa_str}'
    title = f'{obj!s} - {descricao_etapa}'
    is_fic = obj.estrutura_curso.tipo_avaliacao == EstruturaCurso.TIPO_AVALIACAO_FIC
    tab = request.GET.get('tab', '')

    MATRICULADO = SituacaoMatriculaPeriodo.MATRICULADO
    qtd_avaliacoes = obj.componente_curricular.qtd_avaliacoes
    professor_diario = get_object_or_404(obj.professordiario_set, professor__vinculo__user=request.user)
    if not professor_diario.ativo:
        return httprr('/edu/meus_diarios/', f'Vínculo com o diário {diario_pk} inativo', 'error')

    if professor_diario and 'del_pi' in request.GET:
        pi = obj.projetointegrador_set.get(pk=request.GET['del_pi'])
        pi.delete()
        return httprr(f'{request.path}?tab=pi', 'Projeto integrador excluído com sucesso.')

    materiais_professor = professor_diario.materialdiario_set.all().order_by('-data_vinculacao')
    materias_outros = (
        MaterialDiario.objects.filter(professor_diario__diario=obj)
        .exclude(id__in=materiais_professor.values_list('id', flat=True))
        .order_by('-material_aula__data_cadastro')
    )
    data_atual = datetime.date.today()

    q = request.GET.get('q')
    if q:
        materiais_professor = materiais_professor.filter(material_aula__descricao__unaccent__icontains=q)
        materias_outros = materias_outros.filter(material_aula__descricao__unaccent__icontains=q)

    if request.GET.get('xls'):
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename=meu_diario.xlsx'

        cabecalho = ['#', 'Matrícula', 'Nome', 'T. Faltas', '%Freq', 'Situação']
        if obj.componente_curricular.qtd_avaliacoes > 0:
            for avaliacao in range(1, obj.componente_curricular.qtd_avaliacoes + 1):
                cabecalho.append(f'Nota Etapa {avaliacao}')
                cabecalho.append(f'Falta Etapa {avaliacao}')
            cabecalho += ['MD', 'Nota Etapa Final', 'MFD/Conceito']

        data_sheet1 = []
        count = 0
        for matricula_diario in obj.matriculadiario_set.all():
            count += 1
            row = [
                format_(count),
                format_(matricula_diario.matricula_periodo.aluno.matricula),
                format_(normalizar_nome_proprio(matricula_diario.matricula_periodo.aluno.get_nome_social_composto())),
                format_(matricula_diario.get_numero_faltas()),
                format_(matricula_diario.get_percentual_carga_horaria_frequentada()),
                format_(matricula_diario.get_situacao_diario()['rotulo']),
            ]
            if matricula_diario.diario.componente_curricular.qtd_avaliacoes > 0:
                row.append(format_(matricula_diario.get_nota_boletim(1)))
                row.append(format_(matricula_diario.get_numero_faltas_primeira_etapa()))
            if matricula_diario.diario.componente_curricular.qtd_avaliacoes > 1:
                row.append(format_(matricula_diario.get_nota_boletim(2)))
                row.append(format_(matricula_diario.get_numero_faltas_segunda_etapa()))
            if matricula_diario.diario.componente_curricular.qtd_avaliacoes > 2:
                row.append(format_(matricula_diario.get_nota_boletim(3)))
                row.append(format_(matricula_diario.get_numero_faltas_terceira_etapa()))
            if matricula_diario.diario.componente_curricular.qtd_avaliacoes > 3:
                row.append(format_(matricula_diario.get_nota_boletim(4)))
                row.append(format_(matricula_diario.get_numero_faltas_quarta_etapa()))
            if matricula_diario.diario.componente_curricular.qtd_avaliacoes > 0:
                row.append(format_(matricula_diario.get_media_disciplina_boletim()))
                row.append(format_(matricula_diario.get_nota_boletim(5)))
                row.append(format_(matricula_diario.get_media_final_disciplina_boletim()))
            data_sheet1.append(row)

        df1 = pd.DataFrame(data_sheet1, columns=cabecalho)

        cabecalho_sheet2 = ['#', 'Etapa', 'Qtd.', 'Data', 'Professor', 'Conteúdo']
        data_sheet2 = []
        count = 0
        for aula in obj.get_aulas():
            count += 1
            row = [
                format_(count),
                format_(aula.etapa),
                format_(aula.quantidade),
                format_(aula.data),
                format_(str(aula.professor_diario.professor)),
                format_(retira_caracteres_ocultos(aula.conteudo)),
            ]
            data_sheet2.append(row)

        df2 = pd.DataFrame(data_sheet2, columns=cabecalho_sheet2)

        with pd.ExcelWriter(response, engine='openpyxl') as writer:
            df1.to_excel(writer, sheet_name='Dados gerais', index=False)
            df2.to_excel(writer, sheet_name='Registros de Aulas', index=False)

        return response

    em_posse_do_registro = obj.em_posse_do_registro(etapa)
    etapas_anteriores_entegues = obj.etapas_anteriores_entegues(etapa)

    qtd_professores = obj.professordiario_set.filter(ativo=True).count()
    pode_lancar_nota = obj.estrutura_curso.pode_lancar_nota_fora_do_prazo

    pode_manipular_etapa_1 = (
        etapa == 1
        and professor_diario.ativo
        and not em_posse_do_registro
        and (
            qtd_professores == 1
            or pode_lancar_nota
            or (
                professor_diario.data_inicio_etapa_1
                and professor_diario.data_fim_etapa_1
                and data_atual >= professor_diario.data_inicio_etapa_1
                and data_atual <= professor_diario.data_fim_etapa_1
            )
        )
    )
    pode_manipular_etapa_2 = (
        etapa == 2
        and professor_diario.ativo
        and not em_posse_do_registro
        and (
            qtd_professores == 1
            or pode_lancar_nota
            or (
                professor_diario.data_inicio_etapa_2
                and professor_diario.data_fim_etapa_2
                and data_atual >= professor_diario.data_inicio_etapa_2
                and data_atual <= professor_diario.data_fim_etapa_2
            )
        )
    )
    pode_manipular_etapa_3 = (
        etapa == 3
        and professor_diario.ativo
        and not em_posse_do_registro
        and (
            qtd_professores == 1
            or pode_lancar_nota
            or (
                professor_diario.data_inicio_etapa_3
                and professor_diario.data_fim_etapa_3
                and data_atual >= professor_diario.data_inicio_etapa_3
                and data_atual <= professor_diario.data_fim_etapa_3
            )
        )
    )
    pode_manipular_etapa_4 = (
        etapa == 4
        and professor_diario.ativo
        and not em_posse_do_registro
        and (
            qtd_professores == 1
            or pode_lancar_nota
            or (
                professor_diario.data_inicio_etapa_4
                and professor_diario.data_fim_etapa_4
                and data_atual >= professor_diario.data_inicio_etapa_4
                and data_atual <= professor_diario.data_fim_etapa_4
            )
        )
    )
    pode_manipular_etapa_5 = (
        etapa == 5
        and professor_diario.ativo
        and not em_posse_do_registro
        and (
            qtd_professores == 1
            or pode_lancar_nota
            or (
                professor_diario.data_inicio_etapa_final
                and professor_diario.data_fim_etapa_final
                and data_atual >= professor_diario.data_inicio_etapa_final
                and data_atual <= professor_diario.data_fim_etapa_final
            )
        )
    )

    configuracao_avaliacao_selecionada = getattr(obj, f'configuracao_avaliacao_{etapa}')()
    solicitacoes_reposicao_atividade = SolicitacaoReposicaoAtividade.objects.filter(
        item_configuracao_avaliacao__configuracao_avaliacao=configuracao_avaliacao_selecionada
    )

    if etapa == 1:
        inicio_etapa = professor_diario.data_inicio_etapa_1
        fim_etapa = professor_diario.data_fim_etapa_1
        pode_manipular_etapa = pode_manipular_etapa_1
    if etapa == 2:
        inicio_etapa = professor_diario.data_inicio_etapa_2
        fim_etapa = professor_diario.data_fim_etapa_2
        pode_manipular_etapa = pode_manipular_etapa_2
    if etapa == 3:
        inicio_etapa = professor_diario.data_inicio_etapa_3
        fim_etapa = professor_diario.data_fim_etapa_3
        pode_manipular_etapa = pode_manipular_etapa_3
    if etapa == 4:
        inicio_etapa = professor_diario.data_inicio_etapa_4
        fim_etapa = professor_diario.data_fim_etapa_4
        pode_manipular_etapa = pode_manipular_etapa_4
    if etapa == 5:
        inicio_etapa = professor_diario.data_inicio_etapa_final
        fim_etapa = professor_diario.data_fim_etapa_final
        pode_manipular_etapa = pode_manipular_etapa_5

    pode_editar_configuracao_avaliacao = pode_manipular_etapa and (not obj.is_lancamento_conceito() or obj.is_lancamento_conceito() and etapa != 5)

    solicitacao_prorrogacao_pendente = SolicitacaoProrrogacaoEtapa.locals.pendentes().filter(professor_diario=professor_diario, etapa=etapa).exists()

    # exibição das etapas
    etapas = {}
    for numero_etapa in obj.get_lista_etapas():
        dados_etapa = obj.get_etapas().get(numero_etapa)

        if obj.is_semestral_segundo_semestre() and numero_etapa in [1, 2]:
            dados_etapa.update(numero_etapa_exibicao=numero_etapa + 2)

        dados_etapa.update(inicio_etapa=getattr(obj.calendario_academico, 'data_inicio_etapa_{}'.format(dados_etapa['numero_etapa_exibicao'])))
        dados_etapa.update(fim_etapa=getattr(obj.calendario_academico, 'data_fim_etapa_{}'.format(dados_etapa['numero_etapa_exibicao'])))
        dados_etapa.update(inicio_posse=getattr(professor_diario, f'data_inicio_etapa_{numero_etapa}'))
        dados_etapa.update(fim_posse=getattr(professor_diario, f'data_fim_etapa_{numero_etapa}'))
        dados_etapa.update(
            qtd_aulas=obj.get_aulas(numero_etapa).exclude(data__gt=datetime.datetime.now()).aggregate(Sum('quantidade'))['quantidade__sum']
        )
        etapas.update({numero_etapa: dados_etapa})

    dados_etapa_5 = obj.get_etapas().get(5)
    dados_etapa_5.update(inicio_etapa=obj.get_inicio_etapa_final())
    dados_etapa_5.update(fim_etapa=obj.get_fim_etapa_final())
    dados_etapa_5.update(inicio_posse=professor_diario.data_inicio_etapa_final)
    dados_etapa_5.update(fim_posse=professor_diario.data_fim_etapa_final)
    dados_etapa_5.update(qtd_aulas=obj.get_aulas(5).exclude(data__gt=datetime.datetime.now()).aggregate(Sum('quantidade'))['quantidade__sum'])
    etapas.update({'Final': dados_etapa_5})

    aulas = obj.get_aulas(etapa)
    qtd_aulas_passadas = 0
    for aula in aulas:
        if aula.data <= data_atual:
            qtd_aulas_passadas += 1

    acesso_total = True
    materiais_aula = professor_diario.professor.materialaula_set
    if not professor_diario and not request.user.has_group_cached(
        'Administrador Acadêmico,Diretor Acadêmico,Coordenador de Curso, Coordenador de Modalidade Acadêmica,Secretário Acadêmico,Pedagogo'
    ):
        raise PermissionDenied

    polos = obj.get_polos()
    if polo_pk is None:
        polo_pk = polos and polos.first().pk or None
    else:
        polo_pk = int(polo_pk)
    matriculas_diario_por_polo = obj.get_matriculas_diario_por_polo(polo_pk)

    if request.method == 'POST':
        if 'lancamento_nota' in request.POST:
            url = f'/edu/meu_diario/{obj.pk}/{etapa}/?tab=notas'
            try:
                if running_tests():
                    obj.processar_notas(request.POST)
                return httprr(url, 'Notas registradas com sucesso.', anchor='etapa')
            except Exception as e:
                return httprr(url, str(e), 'error', anchor='etapa')

    if tab == 'faltas':
        polos = obj.get_polos()
        boxes_matriculas = []
        for matriculas in matriculas_diario_por_polo:
            for matricula_diario in matriculas:
                matricula_diario.set_faltas(aulas)
            boxes_matriculas.append(matriculas)

    possui_solicitacao_pendente = SolicitacaoRelancamentoEtapa.objects.filter(
        etapa=etapa, professor_diario=professor_diario, data_avaliacao__isnull=True
    ).exists()
    possui_solicitacao_prorrogacao_pendente = SolicitacaoProrrogacaoEtapa.objects.filter(
        etapa=etapa, professor_diario=professor_diario, data_avaliacao__isnull=True
    ).exists()

    topicos = obj.topicodiscussao_set.filter(etapa=etapa)
    trabalhos = obj.trabalho_set.filter(etapa=etapa)

    if tab == 'aulas' or tab == '':
        if inicio_etapa and fim_etapa:
            calendario = Calendario()
            for aula in aulas:
                calendario.adicionar_evento_calendario(aula.data, aula.data, f'{aula.conteudo} ({aula.quantidade} aulas)', 'success', aula.conteudo)
            calendario_diario = calendario.formato_periodo(inicio_etapa.month, inicio_etapa.year, fim_etapa.month, fim_etapa.year)

    if tab == 'estatisticas':
        estatisticas = get_estatisticas_diario(obj)
        if obj.turma.matriz.estrutura.criterio_avaliacao == EstruturaCurso.CRITERIO_AVALIACAO_NOTA:
            # plano de retomada de aulas em virtude da pandemia (COVID19)
            media_aprovacao_avaliacao_final = (
                obj.turma.pertence_ao_plano_retomada and 50 or obj.turma.matriz.estrutura.media_aprovacao_avaliacao_final
            )
            estatisticas['alunos_acima_da_media'] = MatriculaDiario.objects.filter(
                **{
                    'diario': obj,
                    f'nota_{etapa_str}__gt'.lower(): obj.turma.matriz.estrutura.media_aprovacao_sem_prova_final
                    if etapa != 5
                    else media_aprovacao_avaliacao_final,
                }
            ).count()
            estatisticas['alunos_na_media'] = MatriculaDiario.objects.filter(
                **{
                    'diario': obj,
                    f'nota_{etapa_str}'.lower(): obj.turma.matriz.estrutura.media_aprovacao_sem_prova_final
                    if etapa != 5
                    else media_aprovacao_avaliacao_final,
                }
            ).count()
            estatisticas['alunos_abaixo_da_media'] = MatriculaDiario.objects.filter(
                **{
                    'diario': obj,
                    f'nota_{etapa_str}__lt'.lower(): obj.turma.matriz.estrutura.media_aprovacao_sem_prova_final
                    if etapa != 5
                    else media_aprovacao_avaliacao_final,
                }
            ).count()
        else:
            estatisticas['alunos_acima_da_media'] = '-'
            estatisticas['alunos_na_media'] = '-'
            estatisticas['alunos_abaixo_da_media'] = '-'

    exibir_todos_alunos = not obj.matriculadiario_set.filter(situacao=MatriculaDiario.SITUACAO_CURSANDO).exists()
    return locals()


@rtr()
@login_required()
def entregar_etapa(request, diario, etapa):
    obj = get_object_or_404(Diario.locals, pk=diario)

    # obj.turma.curso_campus.plano_ensino é um booleano que indica que é exigido ou não o plano de ensino.
    if obj.turma.curso_campus.plano_ensino and obj.estrutura_curso.exige_plano_ensino_submetido and obj.planoensino_set.all().count() == 1:
        plano_ensino = obj.planoensino_set.first()
        if not plano_ensino.data_submissao:
            return httprr(
                f'/edu/meu_diario/{diario}/{etapa}/',
                'A etapa não pode ser entregue pois o plano de ensino ainda não foi submetido.',
                tag='error',
                close_popup=True,
            )

    if obj.is_lancamento_conceito():
        if (
            etapa != 5
            and ItemConfiguracaoAvaliacao.objects.filter(configuracao_avaliacao__diario_id=diario, configuracao_avaliacao__etapa=etapa)
            .distinct()
            .count()
            < 2
        ):
            return httprr(
                f'/edu/meu_diario/{diario}/{etapa}/?tab=notas',
                'Etapa não pode ser entregue com menos de 2 avaliações cadastradas.',
                tag='error',
                close_popup=True,
            )
        qs = obj.matriculadiario_set.filter(situacao=MatriculaDiario.SITUACAO_CURSANDO)
        if etapa == 1:
            qs = qs.filter(nota_1__isnull=True)
        elif etapa == 2:
            qs = qs.filter(nota_2__isnull=True)
        elif etapa == 3:
            qs = qs.filter(nota_3__isnull=True)
        elif etapa == 4:
            qs = qs.filter(nota_4__isnull=True)
        else:
            qs = qs.filter(nota_final__isnull=True)
        if qs.exists():
            return httprr(
                f'/edu/meu_diario/{diario}/{etapa}/?tab=notas',
                'Etapa não pode ser entregue sem o lançamento do conceito final (CF) de todos alunos.',
                tag='error',
                close_popup=True,
            )

    else:
        qs = obj.matriculadiario_set.filter(nota_final__isnull=False).distinct()
        if qs.exists():
            for matricula_diario in qs:
                if (
                    NotaAvaliacao.objects.filter(
                        matricula_diario=matricula_diario, item_configuracao_avaliacao__configuracao_avaliacao__etapa=5, nota__isnull=False
                    ).exists()
                    and not matricula_diario.is_em_prova_final()
                ):
                    return httprr(
                        f'/edu/meu_diario/{diario}/{etapa}/?tab=notas',
                        f'Etapa não pode ser entregue porque a nota da prova final de {matricula_diario.matricula_periodo.aluno} está inconsistente.',
                        tag='error',
                        close_popup=True,
                    )

    nota_valida_sem_lancamento = NotaAvaliacao.objects.filter(
        matricula_diario_id=OuterRef('id'),
        nota__isnull=True,
        item_configuracao_avaliacao__configuracao_avaliacao__etapa=etapa,
    ).exclude(
        item_configuracao_avaliacao__tipo=ItemConfiguracaoAvaliacao.TIPO_RECUPERACAO,
    )

    qs = (
        obj.matriculadiario_set.filter(
            situacao=MatriculaDiario.SITUACAO_CURSANDO,
        )
        .annotate(
            tem_nota_sem_lancamento=Exists(nota_valida_sem_lancamento),
        )
        .filter(
            tem_nota_sem_lancamento=True,
        )
    )
    pode_entregar_sem_aula = False
    if etapa == 5:
        title = 'Entregar Etapa Final'
        ids = []
        for md in qs:
            if md.get_situacao_nota()['constant'] != MatriculaDiario.SITUACAO_PROVA_FINAL:
                ids.append(md.id)
        qs = qs.exclude(id__in=ids)
    else:
        title = f'Entregar Etapa {etapa}'
        pode_entregar_sem_aula = not obj.get_aulas(etapa) and obj.estrutura_curso.pode_entregar_etapa_sem_aula

    tem_nota_vazia = not obj.is_lancamento_conceito() and qs.exists()

    form = EntregaEtapaForm(data=request.POST or None, tem_nota_vazia=tem_nota_vazia, pode_entregar_sem_aula=pode_entregar_sem_aula)
    if ItemConfiguracaoAvaliacao.objects.filter(
        configuracao_avaliacao__diario=obj,
        configuracao_avaliacao__etapa=etapa,
        solicitacaoreposicaoatividade__deferida=True,
        solicitacaoreposicaoatividade__data_reposicao__isnull=True,
    ).exists():
        form.EXTRA_INFO = '<b>IMPORTANTE</b>: Há solicitações de reposição de atividade pendentes nessa etapa.'
    if form.is_valid():
        try:
            zerar_notas = form.cleaned_data['zerar_notas']
            obj.entregar_etapa_como_professor(etapa, zerar_notas)
        except Exception as e:
            return httprr(f'/edu/meu_diario/{diario}/{etapa}/', str(e), 'error', close_popup=True)
        return httprr(f'/edu/meu_diario/{diario}/{etapa}/', 'Etapa entregue com sucesso.', close_popup=True)
    return locals()


@rtr()
@login_required()
def solicitar_relancamento_etapa(request, professor_diario_pk, etapa):
    title = 'Solicitar Relaçamento de Etapa'
    professor_diario = get_object_or_404(ProfessorDiario, pk=professor_diario_pk)
    form = SolicitarRelancamentoEtapaForm(data=request.POST or None, professor_diario=professor_diario, etapa=etapa)

    if not professor_diario.ativo:
        return httprr('/edu/meus_diarios/', f'Vínculo com o diário {professor_diario.diario} inativo', 'error')

    if form.is_valid():
        form.save()
        return httprr(
            '..', 'Solicitação enviada com sucesso. Assim que sua solicitação for avaliada, você será notificado por e-mail.', anchor='etapa'
        )
    return locals()


@rtr()
@login_required()
def solicitar_prorrogacao_etapa(request, professor_diario_pk, etapa):
    title = 'Solicitar Prorrogação de Etapa'
    professor_diario = get_object_or_404(ProfessorDiario, pk=professor_diario_pk)
    form = SolicitarProrrogacaoEtapaForm(data=request.POST or None, professor_diario=professor_diario, etapa=etapa)

    if not professor_diario.ativo:
        return httprr('/edu/meus_diarios/', f'Vínculo com o diário {professor_diario.diario} inativo', 'error')

    if form.is_valid():
        form.save()
        return httprr(
            '..', 'Solicitação enviada com sucesso. Assim que sua solicitação for avaliada, você será notificado por e-mail.', anchor='etapa'
        )
    return locals()


@rtr()
@permission_required('edu.add_materialaula')
def importar_materiais_aula(request):
    title = 'Importar Materiais de Aula'
    professor = Professor.objects.filter(vinculo=request.user.get_vinculo()).first()
    form = ImportarMaterialAulaForm(professor, data=request.POST or None, request=request)
    if form.is_valid():
        form.processar()
        return httprr('/admin/edu/materialaula/', 'Materiais importados com sucesso.')
    return locals()


@rtr()
@permission_required('edu.add_materialaula')
def adicionar_materiais_aula(request):
    title = 'Adicionar Materiais de Aula'

    form = MateriaisAulaForm(request.POST or None, request=request, files=request.POST and request.FILES or None)

    if form.is_valid():
        notificar, diarios, materiais = form.processar()
        if notificar:
            materiais_str = []
            for material in materiais:
                materiais_str.append('\n\t- ' + material.descricao)

            for diario in diarios:
                matriculas_diarios = MatriculaDiario.objects.filter(diario=diario)
                if matriculas_diarios.exists():
                    disciplina = diario.componente_curricular.componente.descricao
                    vinculos = []
                    for matricula in matriculas_diarios:
                        vinculos.append(matricula.matricula_periodo.aluno.get_vinculo())

                    mensagem = """
        Caro(a) aluno(a),

        Informamos que foi vinculado um novo material à disciplina {}:
        {}

                    """.format(disciplina, ''.join(materiais_str))

                    send_notification(f'[SUAP] Envio de Material - {disciplina}', mensagem, settings.DEFAULT_FROM_EMAIL, vinculos, fail_silently=True)
        return httprr('..', 'Materiais de aula adicionados com sucesso.')
    return locals()


@rtr()
@login_required()
def materiais_diario(request, pk, etapa):
    professor_diario = get_object_or_404(ProfessorDiario, pk=pk)
    is_proprio_professor = professor_diario.professor.vinculo.user.username == request.user.username

    if not is_proprio_professor and not request.user.has_group_cached(
        'Administrador Acadêmico,Diretor Acadêmico,Coordenador de Curso,Coordenador de Modalidade Acadêmica,Secretário Acadêmico,Pedagogo'
    ):
        raise PermissionDenied

    disciplina = professor_diario.diario.componente_curricular.componente.descricao
    title = f'Materiais de Aula do Diário - {disciplina}'
    form = VincularMaterialAulaForm(request.POST or None, request=request, professor_diario=professor_diario)
    if form.is_valid():
        professores_diario = form.processar(etapa)
        matriculas_diarios = MatriculaDiario.objects.filter(
            diario__professordiario__in=professores_diario, situacao__in=[MatriculaDiario.SITUACAO_CURSANDO, MatriculaDiario.SITUACAO_PROVA_FINAL]
        )
        if matriculas_diarios.exists():
            vinculos = []
            for matricula in matriculas_diarios:
                vinculos.append(matricula.matricula_periodo.aluno.get_vinculo())

            materiais = []
            for material in form.cleaned_data['materiais_aula']:
                materiais.append('\n\t- ' + material.descricao)

            mensagem = """
Caro(a) aluno(a),

Informamos que foi vinculado um novo material à disciplina {}:
{}

            """.format(disciplina, ''.join(materiais))

            send_notification(f'[SUAP] Envio de Material - {disciplina}', mensagem, settings.DEFAULT_FROM_EMAIL, vinculos, fail_silently=True)
        return httprr('..', 'Material vinculado com sucesso.', anchor='etapa')
    return locals()


@login_required
@rtr()
def registrar_ocorrencia_diario(request, pk, pk_ocorrencia):
    title = 'Registrar Observação'
    obj = OcorrenciaDiario.objects.filter(pk=pk_ocorrencia).first() or OcorrenciaDiario()
    obj.professor_diario_id = pk
    form = OcorrenciaDiarioForm(data=request.POST or None, instance=obj)
    if form.is_valid():
        form.save()
        return httprr('..', 'Ocorrência registrada com sucesso.')
    return locals()


@rtr()
@login_required()
def disciplina(request, pk):
    obj = get_object_or_404(Diario.objects, pk=pk)
    title = f'Disciplina: {obj}'
    aluno = request.user.get_relacionamento()
    if not isinstance(aluno, Aluno):
        return httprr('/', 'Você não tem permissão para isso', 'erro')
    is_aluno_matriculado = obj.matriculadiario_set.filter(matricula_periodo__aluno=aluno).exists()

    if not is_aluno_matriculado:
        return httprr('/', 'Você não tem permissão para isso', 'erro')
    aulas = obj.get_aulas()
    matricula_diario_qs = obj.matriculadiario_set.filter(matricula_periodo__aluno=aluno)
    if matricula_diario_qs.exists():
        matricula_diario = matricula_diario_qs[0]
        matricula_diario.set_faltas(aulas)
        materiais = MaterialDiario.objects.filter(professor_diario__diario=obj).order_by('-data_vinculacao')
        turnos = obj.get_horarios_aula_por_turno()
    turnos.as_form = False

    topicos = obj.topicodiscussao_set.all()
    trabalhos = []
    for trabalho in obj.trabalho_set.all():
        qs = trabalho.entregatrabalho_set.filter(matricula_diario__matricula_periodo__aluno__matricula=request.user.username)
        trabalho.data_entrega = qs.exists() and qs[0].data_entrega or None
        trabalhos.append(trabalho)

    return locals()


@rtr()
@group_required(
    'Administrador Acadêmico,Diretor Acadêmico,Coordenador de Curso,Coordenador de Modalidade Acadêmica,Secretário Acadêmico,Pedagogo, Professor'
)
def material_aula(request, pk):
    title = 'Visualização de Material de Aula'
    obj = get_object_or_404(MaterialAula, pk=pk, professor__vinculo__user__username=request.user.username)
    return locals()


@rtr()
@login_required()
def disciplinas(request):
    aluno = get_object_or_404(Aluno, matricula=request.user.username)
    periodo_letivo_atual = PeriodoLetivoAtual.get_instance(request, aluno)
    title = f'Minhas disciplinas: {periodo_letivo_atual.ano}.{periodo_letivo_atual.periodo}'
    if aluno.matriculaperiodo_set.exists():
        if aluno.matriculaperiodo_set.filter(ano_letivo__ano=periodo_letivo_atual.ano, periodo_letivo=periodo_letivo_atual.periodo).exists():
            matricula_periodo = aluno.matriculaperiodo_set.get(ano_letivo__ano=periodo_letivo_atual.ano, periodo_letivo=periodo_letivo_atual.periodo)
        else:
            matricula_periodo = None
    else:
        return httprr('/', 'Você ainda não cursou nenhum período.', 'error')
    return locals()


@login_required()
@rtr()
def abonofaltas(request: HttpRequest, pk: int) -> dict[str, Any] | HttpResponse:
    is_popup = '_popup' in request.GET
    obj = AbonoFaltas.objects.filter(pk=pk).first()
    if obj is None:
        return httprr('..', 'Esta justificativa de falta não existe ou foi excluída.', 'error', close_popup=is_popup)
    is_aluno = obj.aluno.matricula == request.user.username
    is_professor_do_diario = False
    professor = Professor.objects.filter(vinculo__user=request.user).first()
    if professor:
        is_professor_do_diario = Falta.objects.filter(
            aula__professor_diario__diario__in=professor.professordiario_set.values_list('diario', flat=True), abono_faltas=obj
        ).exists()

    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, obj.aluno.curso_campus)
    if not is_aluno and not pode_realizar_procedimentos and not is_professor_do_diario and not request.user.has_perm('edu.view_abonofaltas'):
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error', close_popup=is_popup)

    is_avaliado = obj.deferido is not None
    pre_title = 'J' if is_avaliado else 'Solicitação de j'
    title = f'{pre_title}ustificativa de falta: {obj.aluno.pessoa_fisica.nome_usual} ({obj.aluno.matricula})'

    faltas = obj.falta_set.all().order_by('aula__data')
    if pode_realizar_procedimentos and 'cancelar_deferimento' in request.GET:
        obj.cancelar_deferimento()
        return httprr(request.path, 'Cancelamento de deferimento realizado com sucesso.')
    ids_solicitacoes = []
    solicitacoes_reposicao = list(obj.solicitacaoreposicaoatividade_set.all())
    itens_configuracao_avaliacao = list(obj.get_itens_configuracao_avaliacao_periodo())
    exibe_reposicao_atividades = solicitacoes_reposicao or itens_configuracao_avaliacao
    if obj.deferido and request.user.has_group_cached('Professor'):
        ids_solicitacoes = list(
            SolicitacaoReposicaoAtividade.objects.filter(
                abono_faltas=obj, item_configuracao_avaliacao__configuracao_avaliacao__diario__professordiario__professor__vinculo__user=request.user
            ).values_list('pk', flat=True)
        )
    ids_faltas = []
    pode_alterar_abono = obj.motivo_ausencia_escolar is None or not obj.motivo_ausencia_escolar.possui_previsao_normativa
    if professor and pode_alterar_abono:
        ids_faltas = list(obj.falta_set.filter(aula__professor_diario__professor=professor).values_list('pk', flat=True))
        if 'abonar' in request.GET or 'desabonar' in request.GET:
            falta = obj.falta_set.filter(pk__in=ids_faltas).get(pk=request.GET['abonar' if 'abonar' in request.GET else 'desabonar'])
            falta.contabilizar = 'desabonar' in request.GET
            falta.save()
            return httprr(request.path, 'Ação realizada com sucesso.')

    sobreposicoes = []
    if obj.data_inicio and obj.data_fim:
        sobreposicoes = (
            AbonoFaltas.objects.filter(aluno=obj.aluno, data_inicio__lte=obj.data_fim, data_fim__gte=obj.data_inicio)
            .exclude(pk=obj.pk)
            .order_by('data_inicio')
        )

    return locals()


@login_required()
@rtr()
def avaliar_abono_faltas(request: HttpRequest, pk: int) -> dict[str, Any] | HttpResponse:
    obj = get_object_or_404(AbonoFaltas.locals, pk=pk)
    title = 'Avaliar Justificativa de Falta'
    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, obj.aluno.curso_campus)
    if not pode_realizar_procedimentos:
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error', close_popup=True)
    form = AvaliarAbonoFaltasForm(data=request.POST or None, instance=obj)
    if form.is_valid():
        obj = form.processar(request.user)
        obj.checar_solicitacoes_reposicao_atividade()
        if obj.abono_a_criterio_do_docente():
            msg = (
                'Sua justificativa de falta foi deferida. Como o motivo apresentado não possui previsão normativa '
                'para abono automático, a avaliação e o abono das faltas devem ser realizados pelo professor '
                'da disciplina. Acesse o SUAP para obter mais detalhes.'
            )
        else:
            msg = 'Sua justificativa de falta foi avaliada. Acesse o SUAP para obter mais detalhes.'
        send_notification('Avaliação de Justificativa de Falta', msg, settings.DEFAULT_FROM_EMAIL, [obj.aluno.get_vinculo()], fail_silently=True)
        return httprr('..', 'Avaliação realizada com sucesso')
    return locals()


@rtr()
@login_required()
@permission_required('edu.add_abonofaltas')
def abonar_faltas_lote(request):
    title = 'Adicionar Justificativa de Falta em Lote'
    form = AbonoFaltasLoteForm(request.POST or None, files=request.FILES or None, request=request)

    if form.is_valid():
        form.processar()
        return httprr('/admin/edu/abonofaltas/')

    return locals()


@rtr()
@login_required()
def listar_diarios_matricula_aluno(request, matricula_periodo_pk):
    title = 'Matricular em Diário'
    matricula_periodo = get_object_or_404(MatriculaPeriodo, pk=matricula_periodo_pk)

    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, matricula_periodo.aluno.curso_campus)
    if not pode_realizar_procedimentos or not matricula_periodo.pode_matricular_diario():
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    diarios_matriculados = Diario.objects.none()
    if int(request.GET.get('page', 1)) == 1:
        diarios_matriculados = Diario.objects.filter(id__in=matricula_periodo.matriculadiario_set.values_list('diario__id', flat=True))

    remover_diario_id = request.GET.get('remover_diario_id')
    if remover_diario_id:
        md = matricula_periodo.matriculadiario_set.filter(diario__id=remover_diario_id).first()
        if md and md.can_delete():
            md.delete()
            return httprr(request.META.get('HTTP_REFERER', '.'), 'Aluno removido do diário com sucesso.')
        else:
            return httprr(
                request.META.get('HTTP_REFERER', '.'),
                'O aluno não pode ser removido do diário pois ele possui falta/nota lançada no sistema',
                'error',
            )

    form = ListarDiarioMatriculaAlunoForm(matricula_periodo, request.GET or None)

    if form.is_valid():
        diarios = form.processar()

    return locals()


@rtr()
@login_required()
def alterar_data_vinculo_matricula_aluno(request, pk):
    title = 'Atualizar data de matrícula em diário'
    md = get_object_or_404(MatriculaDiario, pk=pk)
    if not perms.realizar_procedimentos_academicos(request.user, md.diario.turma.curso_campus) or not md.is_cursando():
        return httprr('..', 'Você não tem permissão para isso.', 'error', close_popup=True)
    form = ListarDiariosVinculoAlunoForm(md, request.POST or None)
    if form.is_valid():
        form.processar()
        return httprr('..', 'A data de matrícula no diário foi atualizada.', close_popup=True)
    return locals()


@permission_required('edu.change_turma')
@rtr()
def adicionar_alunos_diario(request, diario_pk):
    diario = get_object_or_404(Diario.locals, pk=diario_pk)
    title = 'Matricular Alunos da Turma no Diário'
    qs_matriculas_periodo_turma = diario.turma.get_matriculas_aptas_adicao_turma(diario)
    form = AdicionarAlunosDiarioForm(qs_matriculas_periodo_turma, request.POST or None)
    if form.is_valid():
        count = form.processar(diario)
        if count:
            return httprr('..', f'{count} aluno(s) matriculado(s) no diário com sucesso.')
        else:
            return httprr('..', 'Nenhum aluno foi matriculado no diário.')
    return locals()


@permission_required('edu.lancar_nota_diario')
@rtr()
def registrar_nota_ajax(request, id_nota_avaliacao, nota=None):
    nota_avaliacao = get_object_or_404(NotaAvaliacao, pk=id_nota_avaliacao)
    etapa = nota_avaliacao.item_configuracao_avaliacao.configuracao_avaliacao.etapa

    if nota_avaliacao.matricula_diario.pode_registrar_nota(etapa, request.user):
        nota_avaliacao.nota = None if nota is None else float(nota)
        nota_avaliacao.save()
        nota_avaliacao.matricula_diario.registrar_nota_etapa(nota_avaliacao.item_configuracao_avaliacao.configuracao_avaliacao.etapa)

        attr_nota = 'nota_{}'.format((int(etapa) == 5 and 'final') or etapa)
        nota_etapa = getattrr(nota_avaliacao.matricula_diario, attr_nota)

        attr_etapa = f'posse_etapa_{etapa}'
        posse_etapa = getattrr(nota_avaliacao.matricula_diario.diario, attr_etapa)

        attr_sem_recuperacao = 'nota_parcial_{}'.format(int(etapa) == 5 and 'final' or etapa)
        nota_etapa_sem_recuperacao = getattrr(nota_avaliacao.matricula_diario, attr_sem_recuperacao)

        dict_resposta = {
            'etapa': '-' if nota_etapa is None else nota_etapa,
            'etapa_sem_recuperacao': '-' if nota_etapa_sem_recuperacao is None else nota_etapa_sem_recuperacao,
            'media': nota_avaliacao.matricula_diario.get_media_disciplina() or '-',
            'media_final': nota_avaliacao.matricula_diario.get_media_final_disciplina() or '-',
            'situacao': nota_avaliacao.matricula_diario.get_situacao_nota(),
            'posse': posse_etapa,
            'em_prova_final': nota_avaliacao.matricula_diario.is_em_prova_final(),
            'prova_final_invalida': not nota_avaliacao.matricula_diario.is_em_prova_final() and nota_avaliacao.matricula_diario.nota_final,
        }
        return JsonResponse(dict_resposta)

    # Sem permissão de lançamento a view caía no retorno implícito None (200 vazio),
    # e o callback JS estourava ao ler retorno.situacao.status (Sentry SUAP-VD7).
    return JsonResponse({'erro': 'Sem permissão para lançar nota nesta etapa.'}, status=403)


@permission_required('edu.lancar_nota_diario')
@rtr()
def registrar_conceito_ajax(request, id_nota_avaliacao, conceito=None):
    nota_avaliacao = get_object_or_404(NotaAvaliacao, pk=id_nota_avaliacao)
    etapa = nota_avaliacao.item_configuracao_avaliacao.configuracao_avaliacao.etapa

    if nota_avaliacao.matricula_diario.pode_registrar_nota(etapa, request.user):
        estrutura = nota_avaliacao.matricula_diario.diario.estrutura_curso
        nota = estrutura.get_nota(conceito)

        nota_avaliacao.nota = None if nota is None else float(nota)
        nota_avaliacao.save()
        attr_nota = 'nota_{}'.format(int(etapa) == 5 and 'final' or etapa)
        attr_etapa = f'posse_etapa_{etapa}'
        nota_etapa = getattrr(nota_avaliacao.matricula_diario, attr_nota)
        posse_etapa = getattrr(nota_avaliacao.matricula_diario.diario, attr_etapa)
        dict_resposta = {
            'etapa': '-' if nota_etapa is None else nota_etapa,
            'media': nota_avaliacao.matricula_diario.get_media_disciplina() or '-',
            'media_final': nota_avaliacao.matricula_diario.get_media_final_disciplina() or '-',
            'situacao': nota_avaliacao.matricula_diario.get_situacao_nota(),
            'posse': posse_etapa,
            'em_prova_final': nota_avaliacao.matricula_diario.is_em_prova_final(),
            'prova_final_invalida': not nota_avaliacao.matricula_diario.is_em_prova_final() and nota_avaliacao.matricula_diario.nota_final,
        }
        return JsonResponse(dict_resposta)

    # Sem permissão de lançamento a view caía no retorno implícito None (200 vazio),
    # e o callback JS estourava ao ler retorno.situacao.status (Sentry SUAP-VD7).
    return JsonResponse({'erro': 'Sem permissão para lançar conceito nesta etapa.'}, status=403)


@permission_required('edu.lancar_nota_diario')
@rtr()
def registrar_conceito_final_ajax(request, id_matricula_diario, etapa, conceito=None):
    matricula_diario = get_object_or_404(MatriculaDiario, pk=id_matricula_diario)

    if matricula_diario.pode_registrar_nota(etapa, request.user):
        estrutura = matricula_diario.diario.estrutura_curso
        nota = estrutura.get_nota(conceito)

        attr_nota = 'nota_{}'.format(int(etapa) == 5 and 'final' or etapa)
        setattr(matricula_diario, attr_nota, nota)
        matricula_diario.save()

        if etapa == 5:
            NotaAvaliacao.objects.filter(
                matricula_diario_id=id_matricula_diario, item_configuracao_avaliacao__configuracao_avaliacao__etapa=5
            ).update(nota=nota)

        attr_etapa = f'posse_etapa_{etapa}'
        posse_etapa = getattrr(matricula_diario.diario, attr_etapa)
        dict_resposta = {
            'etapa': '-' if nota is None else nota,
            'media': matricula_diario.get_media_disciplina() or '-',
            'media_final': matricula_diario.get_media_final_disciplina() or '-',
            'situacao': matricula_diario.get_situacao_nota(),
            'posse': posse_etapa,
            'em_prova_final': matricula_diario.is_em_prova_final(),
            'prova_final_invalida': not matricula_diario.is_em_prova_final() and matricula_diario.nota_final,
        }
        return JsonResponse(dict_resposta)

    # Sem permissão de lançamento a view caía no retorno implícito None (200 vazio),
    # e o callback JS estourava ao ler retorno.situacao.status (Sentry SUAP-TEQ/SUAP-VDM).
    return JsonResponse({'erro': 'Sem permissão para registrar conceito nesta etapa.'}, status=403)


@rtr()
@group_required('Administrador Acadêmico,Diretor Acadêmico,Secretário Acadêmico')
def exibir_diarios_fechamento(request, pk, modulo=None):
    title = 'Diários'
    matricula_periodo = MatriculaPeriodo.objects.get(pk=pk)
    diarios = matricula_periodo.get_matriculas_diario_ativas(modulo)
    return locals()


@group_required('Administrador Acadêmico, Diretor Acadêmico, Coordenador de Curso, Coordenador de Modalidade Acadêmica, Secretário Acadêmico')
@rtr()
@login_required()
def exportar_xml_time_tables(request):
    title = 'Exportar XML para o TimeTables'
    form = SelecionarHorarioCampusExportarXMLTimeTables(data=request.POST or None)

    if form.is_valid():
        ano_letivo, periodo_letivo, horario_campus, diretoria = form.processar()
        pks_cursos_ativos = CursoCampus.objects.filter(diretoria=diretoria, ativo=True).values_list('pk', flat=True)

        campus_siape = UnidadeOrganizacional.objects.siape().filter(sigla=diretoria.setor.uo.sigla)
        turmas = Turma.objects.filter(curso_campus__in=pks_cursos_ativos, ano_letivo=ano_letivo, periodo_letivo=periodo_letivo).order_by('codigo')
        diarios = Diario.objects.filter(turma__in=turmas.values_list('pk', flat=True)).order_by('componente_curricular__componente__descricao')

        servidores = Servidor.objects.filter(setor_lotacao__uo__in=campus_siape)
        professores = Professor.servidores_docentes.filter(
            vinculo__id_relacionamento__in=Subquery(servidores.values('id')), vinculo__tipo_relacionamento__model='servidor'
        )

        salas = Sala.ativas.filter(predio__uo=diretoria.setor.uo)

        return render(request, 'exportar_xml_time_tables.xml', locals(), content_type='application/xml')

    return locals()


@group_required('Administrador Acadêmico, Diretor Acadêmico, Coordenador de Curso, Coordenador de Modalidade Acadêmica, Secretário Acadêmico')
@rtr()
@login_required()
def importar_xml_time_tables(request):
    title = 'Importar o XML do TimeTables'
    form = ImportarXMLTimeTables(data=request.POST or None, files=request.FILES or None)

    if form.is_valid():
        exception_msg = 'Erro ao processar o XML do TimeTables. Verifique se o formato do arquivo está correto e tente novamente'
        try:
            form.processar()
            return httprr('..', 'Importação realizada com sucesso!')
        except KeyError as e:
            return httprr('/edu/importar_xml_time_tables/', f'{exception_msg}. Chave {e} não encontrada.', 'error')
        except Exception as e:
            return httprr('/edu/importar_xml_time_tables/', f'{exception_msg}. Detalhe: {e}', 'error')
    return locals()


@rtr()
@login_required()
def grafico_etapa(request, diario_pk, etapa=0):
    etapa = int(etapa)
    if etapa > 5 or etapa < 1:
        return httprr('/edu/meus_diarios/', 'Escolha uma Etapa Válida', 'error')
    descricao_etapa = etapa <= 4 and 'Etapa {}'.format(etapa or 'Etapa Final')
    obj = get_object_or_404(Diario.locals.select_related('componente_curricular__componente_curricular_associado'), pk=diario_pk)
    title = f'Notas dos Alunos na {descricao_etapa}'
    media_etapa = obj.get_media_notas_by_etapa(etapa)
    alunos = []
    i = 1
    dicionario = {f'nota_{etapa}__isnull': False}
    for matricula_diario in obj.matriculadiario_set.filter(**dicionario).order_by('matricula_periodo__aluno__pessoa_fisica__nome'):
        alunos.append({'index': i, 'nome': matricula_diario.matricula_periodo.aluno, 'nota': getattr(matricula_diario, f'nota_{etapa}')})
        i += 1
    return locals()


@rtr('grafico_etapa.html')
@login_required()
def grafico_mfd(request, diario_pk):
    obj = get_object_or_404(Diario.locals.select_related('componente_curricular__componente_curricular_associado'), pk=diario_pk)
    title = 'MFD dos Alunos'
    valores = []
    alunos = []
    i = 1
    for matricula_diario in obj.matriculadiario_set.all().order_by('matricula_periodo__aluno__pessoa_fisica__nome'):
        mfd = matricula_diario.get_media_final_disciplina()
        if mfd is not None:
            valores.append(mfd)
            alunos.append({'index': i, 'nome': matricula_diario.matricula_periodo.aluno, 'nota': mfd})
        i += 1
    media_etapa = len(valores) and sum(valores) / len(valores) or 0
    return locals()


@permission_required('edu.add_observacaodiario')
@rtr()
def adicionar_observacaodiario(request, diario_pk):
    title = ' Adicionar Observação'
    diario = Diario.locals.filter(pk=diario_pk).first()
    if diario:
        form = ObservacaoDiarioForm(diario, request.user, request.POST or None, instance=None)
        if form.is_valid():
            obj = form.save()
            return httprr('..', 'Observação adicionada com sucesso.')
    else:
        return httprr('..', 'Você não tem permissão para modificar os dados deste diário.', 'error')
    return locals()


@permission_required('edu.change_observacaodiario')
@rtr()
def editar_observacaodiario(request, observacao_pk=None):
    title = ' Editar Observação'
    observacao = ObservacaoDiario.objects.get(pk=observacao_pk)
    if request.user == observacao.usuario:
        form = ObservacaoDiarioForm(observacao.diario, request.user, request.POST or None, instance=observacao)
        if form.is_valid():
            obj = form.save()
            return httprr('..', 'Observação atualizada com sucesso.')
    else:
        return httprr('..', 'Você não tem permissão para modificar a obervação de outro usuário.', 'error')
    return locals()


@permission_required('edu.add_itemconfiguracaoavaliacao')
@rtr()
def agendar_avaliacao(request, pk):
    title = 'Agendar Avaliação'
    obj = get_object_or_404(ItemConfiguracaoAvaliacao, pk=pk)
    form = AgendarAvaliacaoForm(data=request.POST or None, instance=obj)
    if form.is_valid():
        form.save()
        return httprr('..', 'Avaliação agendada com sucesso')
    return locals()


@rtr()
def calendario_avaliacao(request, pk=None):
    title = 'Agenda de Avaliações'

    calendario = CalendarioPlus()
    calendario.mostrar_mes_e_ano = True
    calendario.envolve_mes_em_um_box = True
    calendario.destacar_hoje = True
    hoje = datetime.date.today()
    username = request.user.username
    ano_letivo = Ano.objects.get_or_create(ano=hoje.year)[0]
    pks_diario_professor = []
    if pk:
        qs_diarios = Diario.objects.filter(turma_id=pk)
    else:
        qs_diarios = Diario.objects.filter(ano_letivo=ano_letivo)
        diarios_professor = qs_diarios.filter(professordiario__professor__vinculo__user__username=username)
        qs_diarios_aluno = qs_diarios.filter(matriculadiario__matricula_periodo__aluno__vinculos__user__username=username)
        qs_diarios = qs_diarios_aluno | diarios_professor
        pks_diario_professor = list(diarios_professor.values_list('pk', flat=True))
    diarios = []
    possui_avaliacao_agendada = False
    inicio = hoje
    fim = hoje
    for diario in qs_diarios.order_by('pk').distinct('pk'):
        diario.itens_avaliacao = []
        for item_avaliacao in diario.get_itens_avaliacao():
            item_avaliacao.editavel = item_avaliacao.configuracao_avaliacao.diario.pk in pks_diario_professor
            diario.itens_avaliacao.append(item_avaliacao)
            diario.possui_avaliacao_nao_agendada = False
            if item_avaliacao.data:
                possui_avaliacao_agendada = True
                if item_avaliacao.data < inicio:
                    inicio = item_avaliacao.data
                if item_avaliacao.data > fim:
                    fim = item_avaliacao.data
                calendario.adicionar_evento_calendario(
                    data_inicio=item_avaliacao.data,
                    data_fim=item_avaliacao.data,
                    descricao=f'{item_avaliacao.get_tipo_display()} {item_avaliacao.sigla} - {item_avaliacao.get_descricao_etapa()} - {item_avaliacao.configuracao_avaliacao.diario.componente_curricular.componente.descricao_historico}',
                    css_class=item_avaliacao.get_qtd_avaliacoes_concorrentes() > 1 and 'alert' or 'info',
                    title=f'{item_avaliacao.descricao or item_avaliacao.sigla} - {item_avaliacao.configuracao_avaliacao.diario}',
                    url=item_avaliacao.editavel and f'/edu/agendar_avaliacao/{item_avaliacao.pk}/' or None,
                )
            else:
                diario.possui_avaliacao_nao_agendada = True
        diarios.append(diario)
    calendario_html = calendario.formato_periodo(inicio.month, inicio.year, fim.month, fim.year)
    return locals()


@rtr()
@login_required()
def adicionar_topico_discussao(request, pk, etapa):
    title = 'Adicionar Tópico'
    is_aluno_diario = MatriculaDiario.objects.filter(diario__pk=pk, matricula_periodo__aluno__matricula=request.user.username).exists()
    is_professor_diario = ProfessorDiario.objects.filter(diario__pk=pk, professor__vinculo__user=request.user, ativo=True).exists()
    if is_aluno_diario or is_professor_diario:
        diario = get_object_or_404(Diario, pk=pk)
        initial = {'etapa': int(etapa) or None}
        form = TopicoDiscussaoForm(data=request.POST or None, request=request, initial=initial)
        if diario.componente_curricular.qtd_avaliacoes == 1:
            form.fields['etapa'].choices = [[1, 'Etapa 1']]
        if diario.componente_curricular.qtd_avaliacoes == 2:
            form.fields['etapa'].choices = [[1, 'Etapa 1'], [2, 'Etapa 2']]
        if form.is_valid():
            form.save(diario, int(etapa))
            if is_aluno_diario:
                return httprr(f'/edu/disciplina/{pk}/?tab=forum', 'Tópico adicionado com sucesso.', close_popup=True)
            else:
                return httprr(f'/edu/meu_diario/{pk}/{etapa}/?tab=forum', 'Tópico adicionado com sucesso.', close_popup=True)
    else:
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')
    return locals()


@rtr()
@login_required()
def responder_topico_discussao(request, pk):
    title = 'Adicionar Comentário'
    is_aluno_diario = MatriculaDiario.objects.filter(
        diario__topicodiscussao__pk=pk, matricula_periodo__aluno__matricula=request.user.username
    ).exists()
    is_professor_diario = ProfessorDiario.objects.filter(diario__topicodiscussao__pk=pk, professor__vinculo__user=request.user, ativo=True).exists()
    if is_aluno_diario or is_professor_diario:
        topico = get_object_or_404(TopicoDiscussao, pk=pk)
        form = RespostaDiscussaoForm(data=request.POST or None, request=request)
        if form.is_valid():
            form.save(topico)
            return httprr('..', 'Resposta enviada com sucesso.')
    else:
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')
    return locals()


@rtr()
@login_required()
def solicitar_trabalho(request, pk, etapa, pk_trabalho=None):
    title = 'Solicitar Trabalho'
    is_professor_diario = ProfessorDiario.objects.filter(diario__pk=pk, professor__vinculo__user=request.user, ativo=True).exists()
    instance = None
    if pk_trabalho:
        instance = Trabalho.objects.filter(pk=pk_trabalho, diario=pk).first()
        if instance is None:
            return httprr('..', 'Esta solicitação de trabalho não existe.', 'error')
    if is_professor_diario:
        diario = get_object_or_404(Diario, pk=pk)
        form = TrabalhoForm(data=request.POST or None, request=request, files=request.POST and request.FILES or None, instance=instance)
        if form.is_valid():
            form.save(diario, int(etapa))
            return httprr('..', 'Trabalho solicitado com sucesso.')
    else:
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')
    return locals()


@rtr()
@login_required()
def entregar_trabalho(request, pk):
    title = 'Entregar Trabalho'
    is_aluno_diario = MatriculaDiario.objects.filter(diario__trabalho__pk=pk, matricula_periodo__aluno__matricula=request.user.username).exists()
    if is_aluno_diario:
        aluno = request.user.get_vinculo().relacionamento
        trabalho = get_object_or_404(Trabalho.objects.distinct(), pk=pk, diario__matriculadiario__matricula_periodo__aluno=aluno)
        form = EntregaTrabalhoForm(data=request.POST or None, request=request, files=request.POST and request.FILES or None)
        if form.is_valid():
            form.save(trabalho, aluno)
            return httprr('..', 'Trabalho entregue com sucesso.')
    else:
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')
    return locals()


@rtr()
@login_required()
def visualizar_entregas_trabalho(request, pk):
    title = 'Entregas de Trabalho'
    trabalho = get_object_or_404(Trabalho, pk=pk)
    if request.user.pk not in trabalho.diario.professordiario_set.values_list('professor__vinculo__user', flat=True):
        return HttpResponseForbidden()
    return locals()


@rtr()
@login_required()
def avaliar_equivalencia_componente(request, pks):
    title = 'Avaliar Equivalência'
    equivalencias = EquivalenciaComponente.objects.filter(pk__in=pks.split('_')).filter(
        avaliadorequivalenciacomponente__vinculo=request.user.get_vinculo()
    )

    form = AvaliarEquivalenciaComponenteForm(data=request.POST or None, request=request, equivalencias=equivalencias)

    if form.is_valid():
        for equivalencia in equivalencias:
            try:
                avaliacao = equivalencia.avaliadorequivalenciacomponente_set.get(vinculo=request.user.get_vinculo())
            except AvaliadorEquivalenciaComponente.DoesNotExist:
                return httprr('..', 'Você não tem permissão para avaliar esta equivalência.', 'error')
            except AvaliadorEquivalenciaComponente.MultipleObjectsReturned:
                return httprr(
                    '..', 'A configuração de avaliadores está incorreta. Por favor, entre em contato com o responsável pelo cadastro.', 'error'
                )
            if form.cleaned_data.get('aprovada') in ('S', 'N'):
                avaliacao.data_avaliacao = datetime.datetime.now()
                avaliacao.aprovada = form.cleaned_data.get('aprovada') == 'S'
                avaliacao.observacao = form.cleaned_data.get('observacao')
            else:
                avaliacao.aprovada = None
                avaliacao.data_avaliacao = None
                avaliacao.observacao = None
            avaliacao.save()
            total_avaliadores = equivalencia.avaliadorequivalenciacomponente_set.count()
            total_avaliacoes = equivalencia.avaliadorequivalenciacomponente_set.filter(data_avaliacao__isnull=False).count()
            if total_avaliadores and total_avaliacoes == total_avaliadores:
                EquivalenciaComponente.objects.filter(pk=equivalencia.pk).update(
                    aprovada=equivalencia.avaliadorequivalenciacomponente_set.filter(aprovada=True).count() == total_avaliadores
                )
        return httprr('..', 'Avaliação realizada com sucesso.')

    return locals()


@rtr()
@permission_required('edu.view_equivalenciacomponente')
def equivalenciacomponente(request, pk):
    title = 'Equivalência de Componentes'
    obj = get_object_or_404(EquivalenciaComponente, pk=pk)
    is_administrador = request.user.has_perm('comum.is_administrador_academico')

    if is_administrador:
        if 'registrar' in request.GET and obj.is_aprovada():
            obj.identificar_registros_equivalencia(gerar=True)
            return httprr(obj.get_absolute_url(), 'Ação realizada com sucesso.')
        elif 'desfazer' in request.GET:
            obj.excluir_registros()
            return httprr(obj.get_absolute_url(), 'Ação realizada com sucesso.')
        elif 'cancelar_avaliacao' in request.GET:
            obj.cancelar_avaliacao(request.GET['cancelar_avaliacao'])
            return httprr(f'/edu/equivalenciacomponente/{pk}/?tab=avaliadores', 'Cancelamento da avaliação realizado com sucesso.')

    tab = request.GET.get('tab', '')
    if tab == 'avaliadores':
        avaliadores = obj.avaliadorequivalenciacomponente_set.all()
        pode_adicionar_avaliador = obj.pode_adicionar_avaliador(request.user)
    elif tab == 'equivalencias':
        # materializa em lista (evita re-execução de queryset no template).
        # Sem `.only()`: ele deferia `equivalencia_componente_id` da base, e a população da
        # back-reference do related manager recarregava cada linha (N+1, ~81 queries extras).
        equivalencias = list(
            obj.aproveitamentocomponente_set.all().select_related(
                'matricula_periodo__aluno',
                'matricula_periodo__aluno__pessoa_fisica',
                'matricula_periodo__aluno__curso_campus',
                'matricula_periodo__aluno__curso_campus__diretoria__setor',
                'matricula_periodo__aluno__matriz',
            )
        )

    elif tab == 'acoes':
        acoes = [
            f'Equivalência de "{Componente.objects.filter(pk=pk).values_list("sigla", flat=True).first()}" '
            f'com "{", ".join(Componente.objects.filter(pk__in=pks).values_list("sigla", flat=True))}" '
            f'para {aluno}'
            + (f' e remoção do diário "{MatriculaDiario.objects.filter(pk__in=md).values_list("diario", flat=True).first()}"' if md else '')
            for aluno, pk, pks, md in obj.identificar_registros_equivalencia()
        ]

    return locals()


@rtr()
@permission_required('edu.change_equivalenciacomponente')
def adicionar_avaliador_equivalenciacomponente(request, pk):
    title = 'Adicionar avaliador'
    obj = get_object_or_404(EquivalenciaComponente, pk=pk)
    if not obj.pode_adicionar_avaliador(request.user):
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error', close_popup=True)
    form = AvaliadorEquivalenciaComponenteForm(data=request.POST or None, equivalencia=obj)
    if form.is_valid():
        form.save()
        return httprr(obj.get_absolute_url() + '?tab=avaliadores', 'Avaliador adicionado com sucesso.', close_popup=True)
    return locals()
