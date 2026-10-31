import datetime
from typing import Any

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import F
from django.db.models.aggregates import Sum
from django.http import HttpRequest, HttpResponse
from django.http.response import HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.safestring import mark_safe

from comum.models import Ano, Configuracao
from djtools.signals import minhas_acoes
from djtools.utils import (
    JsonResponse,
    XlsResponse,
    group_required,
    httprr,
    ids_da_query,
    mask_ch_componente,
    permission_required,
    rtr,
    send_notification,
)
from edu import perms, tasks
from edu.forms import (
    AbrirPeriodoLetivoForm,
    AddCursoConfiguracaoPedidoMatriculaForm,
    AdicionarAlunoPrimeiraOfertaForm,
    AlunosConflitosHorariosForm,
    AproveitamentoComponenteForm,
    AproveitamentoEstudoForm,
    AtualizarFotosAlunosForm,
    AvaliacaoRequerimentoForm,
    AvaliarSolicitacaoAproveitamentoEstudoForm,
    AvaliarSolicitacaoReposicaoAtividadeForm,
    CadastrarJustificativaFaltaForm,
    CancelarMatriculaForm,
    CertificarConhecimentoForm,
    CreditoEspecialForm,
    EditarMatriculaDiarioResumidaForm,
    EncaminharSolicitacaoAproveitamentoEstudoForm,
    EvasaoEmLoteForm,
    FecharPeriodoLetivoForm,
    ImportacaoAlunosForm,
    ImportarAlunoCSVFormV2,
    ImportarAlunosAtivosForm,
    ImportarComponenteCSVForm,
    ImportarCursoCSVForm,
    ImportarEquivalenciaCSVForm,
    ImportarHistoricoAlunoCSVForm,
    ImportarMatrizCSVForm,
    ImportarProcedimentoMatriculaCSVForm,
    InconsistenciasForm,
    IndeferirRequerimentoEmLoteForm,
    IndeferirRequerimentoForm,
    InicializarPeriodoLetivoForm,
    IntegralizarFaseEscolarForm,
    MatriculaIngressosTurmaForm,
    MatricularAlunoAvulsoDiarioForm,
    MatricularAlunoTurmaForm,
    MatricularDiarioForm,
    MatriculaVinculoForm,
    MedidaDisciplinarForm,
    MonitoramentoEntregaDiariosForm,
    MonitoramentoFechamentoPeriodoForm,
    PremiacaoForm,
    ProcedimentoMatriculaManualForm,
    ReintegrarAlunoForm,
    RelatorioRequerimentoForm,
    ReplicacaoConfiguracaoPedidoMatriculaForm,
    RequerimentoAlunoForm,
    RequerimentoAproveitamentoEstudoForm,
    RequerimentoCancelamentoDisciplinaForm,
    RequerimentoMatriculaComAumentoCHForm,
    RequerimentoMatriculaDiarioForm,
    RequerimentoQuebraRequisitoForm,
    RequerimentoRealizacaoProvaForm,
    RequerimentoTrancamentoMatriculaForm,
    SolicitacaoAproveitamentoEstudoExternoFom,
    SolicitacaoAproveitamentoEstudoInternoFom,
    SolicitarReposicaoAtividadeForm,
    TrancarMatriculaForm,
    TransferenciaCursoForm,
    TransferenciaExternaForm,
)
from edu.models import (
    AbonoFaltas,
    Aluno,
    AproveitamentoComponente,
    AproveitamentoEstudo,
    CertificacaoConhecimento,
    Componente,
    ComponenteCurricular,
    ConfiguracaoPedidoMatricula,
    CreditoEspecial,
    CursoCampus,
    Diario,
    Diretoria,
    EstruturaCurso,
    HorarioAulaDiario,
    MatriculaDiario,
    MatriculaDiarioResumida,
    MatriculaPeriodo,
    MedidaDisciplinar,
    Modalidade,
    NivelEnsino,
    PedidoMatricula,
    PedidoMatriculaDiario,
    PeriodoLetivoAtual,
    PlanoEstudo,
    Premiacao,
    ProcedimentoMatricula,
    ProjetoFinal,
    RegistroConvocacaoENADE,
    Requerimento,
    RequerimentoAproveitamentoEstudo,
    RequerimentoMatriculaComAumentoDeCH,
    RequerimentoMatriculaDisciplina,
    RequerimentoMatriculaQuebraRequisito,
    SituacaoMatriculaPeriodo,
    SolicitacaoAproveitamentoEstudo,
    SolicitacaoReposicaoAtividade,
    Turma,
)
from edu.q_academico import DAO


@minhas_acoes.registrar_acao()
def minhas_acoes(request, data, datahora_inicio, datahora_fim):
    qs = Requerimento.objects.filter(atendente=request.user)

    if datahora_inicio:
        qs = qs.filter(termino__gte=datahora_inicio)
    if datahora_fim:
        qs = qs.filter(termino__lte=datahora_fim)

    tipos = qs.values_list('tipo', flat=True).order_by('tipo').distinct()
    for tipo in tipos:
        for requerimento in qs.filter(tipo=tipo).order_by('termino'):
            data.append(
                (
                    'Ensino',
                    requerimento.get_tipo_display(),
                    f'{requerimento} - {requerimento.aluno}',
                    f'em {requerimento.termino.strftime("%d/%m/%Y %H:%M")}',
                    f'/edu/requerimento/{requerimento.id}/',
                )
            )

    qs1 = AbonoFaltas.objects.filter(responsavel_abono=request.user, data_avaliacao__isnull=True)
    if datahora_inicio:
        qs1 = qs1.filter(data_solicitacao__gte=datahora_inicio)
    if datahora_fim:
        qs1 = qs1.filter(data_solicitacao__lte=datahora_fim)
    qs2 = AbonoFaltas.objects.filter(responsavel_abono=request.user, data_avaliacao__isnull=False)
    if datahora_inicio:
        qs2 = qs2.filter(data_avaliacao__gte=datahora_inicio)
    if datahora_fim:
        qs2 = qs2.filter(data_avaliacao__lte=datahora_fim)
    for abono_faltas in (qs1 | qs2).order_by('data_avaliacao', 'data_solicitacao'):
        if abono_faltas.data_avaliacao:
            data_abono = abono_faltas.data_avaliacao.strftime('%d/%m/%Y')
        else:
            data_abono = abono_faltas.data_solicitacao.strftime('%d/%m/%Y')
        data.append(
            (
                'Ensino',
                'Avaliação de Justificativa de Faltas',
                abono_faltas,
                f'em {data_abono}',
                f'/edu/abonofaltas/{abono_faltas.id}/',
            )
        )

    return data


@rtr()
@permission_required('edu.gerar_relatorio')
def relatorio_requerimentos(request):
    title = 'Relatório de Requerimentos'
    form = RelatorioRequerimentoForm(data=request.POST or None)
    if form.is_valid():
        dados = form.processar()
        return XlsResponse(dados)
    return locals()


@rtr()
def adicionar_requerimento(request, tipo, pk=None):
    title = 'Requerimento'
    instance = pk and get_object_or_404(Requerimento, pk=pk) or None
    aluno = get_object_or_404(Aluno, matricula=request.user.username)
    msg_sucesso = 'Requerimento adicionado com sucesso.'
    if aluno.situacao.ativo:
        form_cls = None
        hoje = datetime.date.today()
        if int(tipo) == Requerimento.TRANCAMENTO_DISCIPLINA:
            form_cls = RequerimentoCancelamentoDisciplinaForm
            form = form_cls(data=request.POST or None, instance=instance, request=request, aluno=aluno)
            if form.is_valid():
                form.save()
                return httprr('..', msg_sucesso)
        elif int(tipo) == Requerimento.MATRICULA_DISCIPLINA:
            form_cls = RequerimentoMatriculaDiarioForm
            form = form_cls(data=request.POST or None, instance=instance, request=request, aluno=aluno)
            if form.is_valid():
                form.save()
                return httprr('..', msg_sucesso)
        elif int(tipo) == Requerimento.TRANCAMENTO_MATRICULA:
            if aluno.pode_solicitar_trancamento_voluntario():
                form_cls = RequerimentoTrancamentoMatriculaForm
                form = form_cls(data=request.POST or None, instance=instance, request=request)
                if form.is_valid():
                    form.instance.tipo = Requerimento.TRANCAMENTO_MATRICULA
                    form.instance.aluno = aluno
                    form.instance.data = hoje
                    form.save()
                    return httprr('..', msg_sucesso)
            else:
                return httprr('..', 'Não é possível solicitar trancamento de matrícula.', 'error')
        elif int(tipo) == Requerimento.APROVEITAMENTO_ESTUDO:
            matricula_periodo = aluno.get_ultima_matricula_periodo()

            pode_solicitar, mensagem = RequerimentoAproveitamentoEstudo.pode_solicitar_requerimento(matricula_periodo)
            if not pode_solicitar:
                return httprr(f'{aluno.get_absolute_url()}?tab=requerimentos', mensagem, 'error', close_popup=True)

            title = 'Requerimento de Aproveitamento de Estudo'
            form_cls = RequerimentoAproveitamentoEstudoForm
            form = form_cls(data=request.POST or None, instance=instance, request=request, files=request.FILES or None)
            form.instance.matricula_periodo = matricula_periodo
            if form.is_valid():
                form.instance.aluno = aluno
                form.instance.data = hoje
                form.save()
                return httprr(
                    f'/edu/requerimento_aproveitamento_estudo/{form.instance.pk}/', 'Informe as disciplinas que deseja aproveitar.', close_popup=True
                )
        elif int(tipo) == Requerimento.REALIZACAO_PROVA:
            form_cls = RequerimentoRealizacaoProvaForm
            form = form_cls(data=request.POST or None, instance=instance, request=request, files=request.FILES or None)
            form.fields['diario'].queryset = Diario.objects.filter(
                id__in=aluno.get_ultima_matricula_periodo().matriculadiario_set.values_list('diario', flat=True)
            )
            form.fields['anexo'].required = True
            if form.is_valid():
                form.instance.tipo = Requerimento.REALIZACAO_PROVA
                form.instance.aluno = aluno
                form.instance.data = hoje
                form.save()
                return httprr('..', msg_sucesso)
        else:
            form = RequerimentoAlunoForm(data=request.POST or None, instance=instance, request=request, files=request.FILES or None)
            form.fields['tipo'].choices = Requerimento.get_aluno_choices()
            if form.is_valid():
                form.instance.aluno = aluno
                form.instance.data = hoje
                form.save()
                return httprr('..', msg_sucesso)
    else:
        return httprr('..', 'Requerimento disponível apenas para alunos ativos.', 'error')
    return locals()


@group_required('Administrador Acadêmico,Diretor Acadêmico,Secretário Acadêmico')
@rtr()
def fechar_periodo_letivo(request):
    periodo_modulo = 'módulo' if request.GET.get('modulo') else 'período letivo'
    title = f'Fechar {periodo_modulo}'
    acao = 'fechar_periodo_letivo'
    situacao_contraria = 'fechado'
    qtd_avaliacoes = 4
    form = FecharPeriodoLetivoForm(data=request.GET or None)

    if form.is_valid():
        if 'finalize' not in request.GET:
            return form.processar(request)
        if form.matriculas_periodo.exists():
            messages.info(
                request, 'Período letivo fechado com sucesso. Os alunos listados abaixo não foram processados por apresentarem alguma pendência.'
            )
        else:
            return httprr('/edu/fechar_periodo_letivo/')
    matriculas_periodo = form.matriculas_periodo

    is_administrador = request.user.has_group_cached('Administrador Acadêmico')
    if not is_administrador and not form.exibir_forcar_fechamento:
        if 'forcar_fechamento' in form.fields:
            form.fields['forcar_fechamento'].widget.attrs.update(disabled='disabled')

    return locals()


@group_required('Administrador Acadêmico,Diretor Acadêmico,Secretário Acadêmico')
@rtr('fechar_periodo_letivo.html')
def abrir_periodo_letivo(request):
    title = 'Abrir Período Letivo'
    acao = 'abrir_periodo_letivo'
    situacao_contraria = 'aberto'
    qtd_avaliacoes = 4
    form = AbrirPeriodoLetivoForm(data=request.GET or None)
    if form.is_valid():
        if 'finalize' not in request.GET:
            return form.processar(request)
        if form.matriculas_periodo.exists():
            messages.info(
                request, 'Período letivo aberto com sucesso. Os alunos listados abaixo não foram processados por apresentarem alguma pendência.'
            )
        else:
            return httprr('/edu/abrir_periodo_letivo/')
    matriculas_periodo = form.matriculas_periodo
    return locals()


@login_required()
@rtr()
def realizar_cancelamento_matricula(request, matricula_periodo_pk):
    title = 'Cancelar Matrícula'
    matricula_periodo = get_object_or_404(MatriculaPeriodo, pk=matricula_periodo_pk)

    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, matricula_periodo.aluno.curso_campus)
    if not pode_realizar_procedimentos or not matricula_periodo.pode_realizar_procedimento_matricula():
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    form = CancelarMatriculaForm(matricula_periodo_pk, request.POST or None, initial={'data': datetime.datetime.today()})
    if form.is_valid():
        form.save()
        return httprr('..', 'Cancelamento realizado com sucesso.')
    return locals()


@login_required()
@rtr()
def realizar_trancamento_matricula(request, matricula_periodo_pk):
    title = 'Trancar Matrícula'
    matricula_periodo = get_object_or_404(MatriculaPeriodo, pk=matricula_periodo_pk)

    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, matricula_periodo.aluno.curso_campus)
    if not pode_realizar_procedimentos:
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    if not matricula_periodo.pode_realizar_procedimento_matricula():
        return httprr('..', 'A matrícula deste aluno não pode ser trancada.', 'error')

    form = TrancarMatriculaForm(matricula_periodo_pk, request.POST or None, initial={'data': datetime.datetime.today()})
    if form.is_valid():
        try:
            form.save()
        except ValidationError as e:
            return httprr(matricula_periodo.aluno.get_absolute_url(), e.message, 'error', close_popup=True)
        return httprr(matricula_periodo.aluno.get_absolute_url(), 'Trancamento realizado com sucesso.', close_popup=True)
    return locals()


@login_required()
@rtr()
def integralizar_fase_escolar(request, matricula_periodo_pk):
    title = 'Integralizar Fase Escolar'
    matricula_periodo = get_object_or_404(MatriculaPeriodo, pk=matricula_periodo_pk)
    is_administrador = request.user.has_group_cached('Administrador Acadêmico')
    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, matricula_periodo.aluno.curso_campus)
    if not pode_realizar_procedimentos:
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    if not is_administrador and not matricula_periodo.pode_integralizar_fase_escolar():
        return httprr(
            '..',
            'O aluno não pode ser integralizado. Certifique-se que sua pasta documental possui o comprovante de aprovação em processo seletivo de graduação, que todas as disciplinas regulares encontram-se cursadas e que apenas a prática profisional esteja pendente.',
            'error',
        )

    form = IntegralizarFaseEscolarForm(matricula_periodo_pk, request.POST or None, initial={'data': datetime.datetime.today()})
    if form.is_valid():
        try:
            form.save()
        except ValidationError as e:
            return httprr(matricula_periodo.aluno.get_absolute_url(), e.message, 'error', close_popup=True)
        return httprr(matricula_periodo.aluno.get_absolute_url(), 'Integralização realizada com sucesso.', close_popup=True)
    return locals()


@transaction.atomic
@login_required()
@rtr()
def realizar_transferencia_curso(request, matricula_periodo_pk, tipo):
    title = f'Transferência - {tipo}'
    matricula_periodo = get_object_or_404(MatriculaPeriodo, pk=matricula_periodo_pk)

    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, matricula_periodo.aluno.curso_campus)
    if not pode_realizar_procedimentos or not matricula_periodo.aluno.get_ultima_matricula_periodo().pode_realizar_transferencia():
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    form = TransferenciaCursoForm(matricula_periodo_pk, tipo, request.POST or None, initial={'data': datetime.datetime.now()})
    if form.is_valid():
        procedimento = form.save()
        aluno = form.instance.matricula_periodo.aluno.clonar(
            form.cleaned_data['matriz_curso'],
            form.cleaned_data['forma_ingresso'],
            form.cleaned_data['turno'],
            data=form.instance.data,
            importar_pasta_documental=form.cleaned_data['importar_pasta_documental'],
            procedimento=procedimento,
        )
        return httprr(
            '..',
            mark_safe(
                f'Transferência realizada com sucesso. (<a target="_blank" href="/edu/comprovante_matricula_pdf/{aluno.pk}/">Imprimir Comprovante</a>) '
            ),
        )
    return locals()


@login_required()
@rtr()
def realizar_transferencia_externa(request, matricula_periodo_pk):
    title = 'Realizar Transferência'

    matricula_periodo = get_object_or_404(MatriculaPeriodo, pk=matricula_periodo_pk)
    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, matricula_periodo.aluno.curso_campus)
    if not pode_realizar_procedimentos or not matricula_periodo.aluno.get_ultima_matricula_periodo().pode_realizar_transferencia():
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    form = TransferenciaExternaForm(matricula_periodo_pk, request.POST or None, initial={'data': datetime.datetime.today()})
    if form.is_valid():
        form.save()
        return httprr('..', 'Transferência externa realizada com sucesso.')
    return locals()


@permission_required('edu.efetuar_matricula')
@rtr()
def realizar_matricula_vinculo(request, matricula_periodo_pk):
    title = 'Realizar Matrícula Vínculo'
    matricula_periodo = get_object_or_404(MatriculaPeriodo, pk=matricula_periodo_pk)
    if not matricula_periodo.is_aberto():
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')
    form = MatriculaVinculoForm(matricula_periodo_pk, request.POST or None, initial={'data': datetime.datetime.today()}, request=request)
    if form.is_valid():
        form.save()
        return httprr('..', 'Matrícula Vínculo realizada com sucesso.')
    return locals()


@group_required('Administrador Acadêmico')
@rtr()
def importar_alunos(request):
    title = 'Importar Alunos do Q-Acadêmico'
    form = ImportacaoAlunosForm(request.POST or None)
    if form.is_valid():
        form.processar()
        return httprr('/admin/edu/historicoimportacao/', 'Alunos importados com sucesso.')

    return locals()


@login_required()
@rtr()
def reintegrar_aluno(request, matricula_periodo_pk):
    title = 'Reintegrar Aluno'
    matricula_periodo = get_object_or_404(MatriculaPeriodo, pk=matricula_periodo_pk)

    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, matricula_periodo.aluno.curso_campus)
    if not pode_realizar_procedimentos:
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    if not matricula_periodo.is_cancelado():
        return httprr('..', 'Impossível reintegrar aluno.', 'error')

    form = ReintegrarAlunoForm(matricula_periodo, data=request.POST or None, initial={'data': datetime.datetime.today()})
    if form.is_valid():
        ano_letivo = form.cleaned_data['ano_letivo']
        periodo_letivo = form.cleaned_data['periodo_letivo']

        procedimento = form.save(commit=False)
        procedimento.tipo = 'Reintegração'
        procedimento.situacao_matricula_anterior = matricula_periodo.aluno.situacao

        matricula_periodo.reintegrar_aluno(procedimento, ano_letivo, periodo_letivo)
        return httprr('..', 'Aluno reintegrado com sucesso.')
    return locals()


@login_required()
@rtr()
def calcular_ira_parcial(request, aluno_pk):
    aluno = get_object_or_404(Aluno, pk=aluno_pk)
    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, aluno.curso_campus)
    if not pode_realizar_procedimentos:
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')
    ira_parcial = aluno.calcular_indice_rendimento(parcial=True)
    return locals()


@login_required()
@rtr()
def certificar_conhecimento(request, aluno_pk, componente_curricular_pk):
    componente_curricular = get_object_or_404(ComponenteCurricular, pk=componente_curricular_pk)
    title = f'Certificar Conhecimento - {componente_curricular.componente.descricao_historico}'
    aluno = get_object_or_404(Aluno, pk=aluno_pk)

    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, aluno.curso_campus)
    if not pode_realizar_procedimentos:
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    extrapola_percentual_max_aproveitamento = False
    if aluno.matriz.estrutura.percentual_max_aproveitamento:
        ch_componentes_aproveitaveis = aluno.matriz.get_ch_certificavel_aproveitavel()
        extrapola_percentual_max_aproveitamento = (
            aluno.get_ch_certificada_ou_aproveitada() + componente_curricular.get_carga_horaria_total()
            > aluno.matriz.estrutura.percentual_max_aproveitamento * ch_componentes_aproveitaveis / 100
        )
    extrapola_quantidade_max_creditos_aproveitamento = False
    if aluno.matriz.estrutura.quantidade_max_creditos_aproveitamento:
        extrapola_quantidade_max_creditos_aproveitamento = (
            aluno.get_creditos_certificados_ou_aproveitados() + componente_curricular.componente.ch_qtd_creditos
            > aluno.matriz.estrutura.quantidade_max_creditos_aproveitamento
        )
    matriculas_diario = MatriculaDiario.objects.filter(
        situacao=MatriculaDiario.SITUACAO_CURSANDO,
        matricula_periodo__aluno=aluno,
        diario__componente_curricular__componente=componente_curricular.componente.pk,
    )
    qs = CertificacaoConhecimento.objects.filter(componente_curricular=componente_curricular, matricula_periodo__aluno=aluno)
    instance = qs.exists() and qs[0] or None
    form = CertificarConhecimentoForm(aluno, componente_curricular, request.POST or None, instance=instance, request=request)
    if form.is_valid():
        certificacao = form.save()
        if certificacao.is_aluno_aprovado():
            matriculas_diario.delete()
        return httprr('..', 'Certificação cadastrada com sucesso.')
    return locals()


@login_required()
@rtr()
def aproveitar_estudo(request, aluno_pk, componente_curricular_pk):
    componente_curricular = get_object_or_404(ComponenteCurricular, pk=componente_curricular_pk)
    title = f'Aproveitar Estudo - {componente_curricular.componente.descricao_historico}'
    aluno = get_object_or_404(Aluno, pk=aluno_pk)

    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, aluno.curso_campus)
    if not pode_realizar_procedimentos:
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    extrapola_percentual_max_aproveitamento = False
    if (
        aluno.matriz.estrutura.percentual_max_aproveitamento
        and not aluno.matriz.estrutura.formas_ingresso_ignoradas_aproveitamento.filter(pk=aluno.forma_ingresso.pk).exists()
    ):
        ch_componentes_aproveitaveis = aluno.matriz.get_ch_certificavel_aproveitavel()
        extrapola_percentual_max_aproveitamento = (
            aluno.get_ch_certificada_ou_aproveitada() + componente_curricular.get_carga_horaria_total()
            > aluno.matriz.estrutura.percentual_max_aproveitamento * ch_componentes_aproveitaveis / 100
        )
    extrapola_quantidade_max_creditos_aproveitamento = False
    if aluno.matriz.estrutura.quantidade_max_creditos_aproveitamento:
        extrapola_quantidade_max_creditos_aproveitamento = (
            aluno.get_creditos_certificados_ou_aproveitados() + componente_curricular.componente.ch_qtd_creditos
            > aluno.matriz.estrutura.quantidade_max_creditos_aproveitamento
        )

    matriculas_diario = MatriculaDiario.objects.filter(
        situacao=MatriculaDiario.SITUACAO_CURSANDO,
        matricula_periodo__aluno=aluno,
        diario__componente_curricular__componente_id=componente_curricular.componente.id,
    )
    qs = AproveitamentoEstudo.objects.filter(componente_curricular__componente=componente_curricular.componente.pk, matricula_periodo__aluno=aluno)
    instance = qs.first()
    form = AproveitamentoEstudoForm(aluno, componente_curricular, request.POST or None, instance=instance, request=request)
    if form.is_valid():
        aproveitamento = form.save()
        matriculas_diario.delete()
        return httprr('..', 'Aproveitamento adicionado com sucesso.')
    return locals()


@login_required()
@rtr()
def aproveitar_componente(request, aluno_pk, componente_curricular_pk):
    componente_curricular = get_object_or_404(ComponenteCurricular, pk=componente_curricular_pk)
    title = f'{componente_curricular.componente.descricao} - {componente_curricular.componente.get_ch_hora_relogio()} h'
    aluno = get_object_or_404(Aluno, pk=aluno_pk)

    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, aluno.curso_campus)
    if not pode_realizar_procedimentos:
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    matriculas_diario = MatriculaDiario.objects.filter(
        situacao=MatriculaDiario.SITUACAO_CURSANDO, matricula_periodo__aluno=aluno, diario__componente_curricular=componente_curricular
    )
    qs = AproveitamentoComponente.objects.filter(componente_curricular=componente_curricular, matricula_periodo__aluno=aluno)
    instance = qs.exists() and qs[0] or None
    form = AproveitamentoComponenteForm(aluno, componente_curricular, request.POST or None, instance=instance)
    if form.is_valid():
        aproveitamento = form.save()
        matriculas_diario.delete()
        return httprr('..', 'Equivalência cadastrada com sucesso.')
    return locals()


@permission_required('edu.efetuar_matricula')
@rtr()
def evadir_alunos_selecionados(request):
    if 'alunos_selecionados' in request.POST:
        ids = request.POST.getlist('alunos_selecionados')
        if ids:
            alunos_selecionados = Aluno.locals.filter(id__in=ids)
            return tasks.evadir_alunos_lote(alunos_selecionados)
    else:
        return httprr('/')


@permission_required('edu.efetuar_matricula')
@rtr()
def evasao_em_lote(request):
    title = 'Evasão em Lote'
    form = EvasaoEmLoteForm(data=request.GET or None)
    if form.is_valid():
        alunos = form.processar()
        if 'xls' in request.GET:
            return tasks.exportar_evasao_em_lote_xls(alunos)
    return locals()


@permission_required('edu.efetuar_matricula')
@rtr()
def evadir_aluno(request, pk):
    aluno = get_object_or_404(Aluno.locals, pk=pk)
    try:
        aluno.get_ultima_matricula_periodo().evadir('Evasão Individual')
        return httprr(f'/edu/aluno/{aluno.matricula}', 'Aluno evadido com sucesso.')
    except ValidationError as e:
        return httprr(f'/edu/aluno/{aluno.matricula}', f'{e.messages[0]} de evasão.', 'error')


@rtr()
@login_required()
def matricular_aluno_diario(request, matricula_periodo_pk, diario_pk):
    title = 'Matricular em Diário'
    matricula_periodo = get_object_or_404(MatriculaPeriodo, pk=matricula_periodo_pk)
    diario = get_object_or_404(Diario, pk=diario_pk)

    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, matricula_periodo.aluno.curso_campus)
    if not pode_realizar_procedimentos or not matricula_periodo.pode_matricular_diario():
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    alertas = []

    pode_matricular, msg = matricula_periodo.aluno.pode_ser_matriculado_no_diario(diario)
    if not pode_matricular:
        return httprr('..', msg, 'error')
    if pode_matricular and msg:
        alertas.append(msg)

    if not diario.horarioauladiario_set.exists():
        alertas.append('Diário sem horário definido.')

    if matricula_periodo.atingiu_qtd_maxima_disciplinas():
        alertas.append('A matricula do aluno no diário, excede o número máximo de disciplinas permitidas para o período de referência.')

    if matricula_periodo.atingiu_ch_maxima_disciplinas(diario):
        alertas.append('A matricula do aluno no diário, excede a carga horária máxima de disciplinas permitidas para o período.')

    form = MatricularDiarioForm(request.POST or None)
    if form.is_valid():
        form.processar(matricula_periodo, diario)
        return httprr('..', 'Aluno matriculado com sucesso.')

    return locals()


@rtr()
@login_required()
def matricular_aluno_turma(request, aluno_pk):
    title = 'Matricular em Turma'
    aluno = get_object_or_404(Aluno, pk=aluno_pk)
    matricula_periodo = aluno.get_ultima_matricula_periodo()

    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, aluno.curso_campus)
    if (
        not pode_realizar_procedimentos
        or not matricula_periodo.pode_matricular_diario()
        or aluno.matriz.estrutura.tipo_avaliacao not in [EstruturaCurso.TIPO_AVALIACAO_SERIADO, EstruturaCurso.TIPO_AVALIACAO_MODULAR]
    ):
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    if matricula_periodo.turma:
        return httprr('..', 'O aluno selecionado já possui uma turma.', 'error')

    form = MatricularAlunoTurmaForm(matricula_periodo, data=request.POST or None)

    if form.is_valid():
        form.processar()
        return httprr('..', 'O aluno foi matriculado na turma com sucesso.')

    return locals()


@rtr()
@permission_required('edu.reabrir_diario')
def matricular_aluno_avulso_diario(request, diario_pk):
    title = 'Adicionar aluno em diário'

    diario = get_object_or_404(Diario, pk=diario_pk)
    form = MatricularAlunoAvulsoDiarioForm(diario, request.POST or None, request=request)
    if form.is_valid():
        form.processar()
        return httprr('..', 'Aluno matriculado com sucesso.')

    return locals()


@rtr()
@permission_required('edu.reabrir_diario')
def adicionar_aluno_primeira_oferta(request, diario_pk):
    title = 'Adicionar aluno da primeira oferta'

    diario = get_object_or_404(Diario, pk=diario_pk)
    form = AdicionarAlunoPrimeiraOfertaForm(request.POST or None, diario=diario)
    if form.is_valid():
        form.processar()
        return httprr('..', 'Aluno adicionado com sucesso.')

    return locals()


@login_required()
@rtr()
def cancelar_matricula_diario(request, matricula_diario_pk):
    matricula_diario = get_object_or_404(MatriculaDiario, pk=matricula_diario_pk)
    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, matricula_diario.matricula_periodo.aluno.curso_campus)
    url = request.META.get('HTTP_REFERER', '.')
    if not pode_realizar_procedimentos:
        return httprr(url, 'Você não tem permissão para realizar isso.', 'error')
    try:
        matricula_diario.cancelar()
    except ValidationError as e:
        return httprr(url, e.message, 'error')

    return httprr(url, 'Matrícula em diário cancelada com sucesso.')


@login_required()
@rtr()
def desfazer_cancelamento_matricula_diario(request, matricula_diario_pk):
    matricula_diario = MatriculaDiario.objects.get(pk=matricula_diario_pk)
    ultima_matricula_periodo = matricula_diario.matricula_periodo.aluno.get_ultima_matricula_periodo()

    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, ultima_matricula_periodo.aluno.curso_campus)
    if not pode_realizar_procedimentos:
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    if not (
        matricula_diario.matricula_periodo.ano_letivo.ano == ultima_matricula_periodo.ano_letivo.ano
        and matricula_diario.matricula_periodo.periodo_letivo == ultima_matricula_periodo.periodo_letivo
    ):
        return httprr(
            f'{matricula_diario.matricula_periodo.aluno.get_absolute_url()}?tab=historico',
            'Não é possível desfazer o cancelamento devido ao diário não ser do período corrente do aluno.',
            'error',
        )

    if (
        matricula_diario.diario.possui_segunda_oferta
        and MatriculaDiario.objects.filter(
            diario__diario_primeira_oferta_id=matricula_diario.diario_id, matricula_periodo_id=matricula_diario.matricula_periodo_id
        ).exists()
    ):
        return httprr(
            f'{matricula_diario.matricula_periodo.aluno.get_absolute_url()}?tab=historico',
            'Não é possível desfazer o cancelamento pois o aluno está cursando este componente em diário de segunda oferta.',
            'error',
        )

    matricula_diario.situacao = MatriculaDiario.SITUACAO_CURSANDO
    matricula_diario.save()

    return httprr(
        f'{matricula_diario.matricula_periodo.aluno.get_absolute_url()}?tab=historico', 'Cancelamento de matrícula em diário desfeito com sucesso.'
    )


@rtr()
@login_required()
def pedido_matricula_seriado(request, aluno_pk):
    aluno = get_object_or_404(Aluno.locals, pk=aluno_pk)

    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, aluno.curso_campus)
    if not pode_realizar_procedimentos and not aluno.is_user(request):
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    if not aluno.pode_matricula_online() or aluno.is_credito():
        return httprr('/', 'Não existe um período de renovação de matrícula ativa para o seu curso.', 'error')

    configuracao_pedido_matricula_ativa = aluno.get_configuracao_pedido_matricula_ativa()
    if aluno.is_user(request) and configuracao_pedido_matricula_ativa.requer_atualizacao_dados and 'dados_atualizados' not in request.session:
        return httprr(f'/edu/atualizar_meus_dados_pessoais/{aluno.matricula}/1/')

    if (
        aluno.is_user(request)
        and configuracao_pedido_matricula_ativa.requer_atualizacao_caracterizacao
        and 'caracterizacao_atualizada' not in request.session
    ):
        return httprr(f'/ae/caracterizacao/{aluno.pk}/1/')

    ultima_matricula_periodo = aluno.get_ultima_matricula_periodo()
    segunda_chamada = ultima_matricula_periodo.situacao.pk in [
        SituacaoMatriculaPeriodo.MATRICULA_VINCULO_INSTITUCIONAL,
        SituacaoMatriculaPeriodo.MATRICULADO,
    ]
    title = 'Matrícula Online ({})'.format(segunda_chamada and '2ª Chamada' or '1ª Chamada')

    # obtendo as turmas com seus diários disponíveis para o aluno
    turmas = aluno.get_turmas_matricula_online(restringir_por_convenio=configuracao_pedido_matricula_ativa.restringir_por_convenio)

    # obtendo os diários das disciplinas em dependência do aluno
    diarios_dependencia = aluno.get_diarios_pendentes_matricula_online(
        apenas_obrigatorias=True,
        ignorar_pendencia_horario=aluno.curso_campus.modalidade.pk in [Modalidade.INTEGRADO, Modalidade.SUBSEQUENTE],
        restringir_por_convenio=configuracao_pedido_matricula_ativa.restringir_por_convenio,
    )

    # Verificando se existe algum diário disponível nas turmas disponíveis
    diarios_disponiveis_turma = False
    for turma in turmas:
        if turma.diarios:
            diarios_disponiveis_turma = True

    # Obtendo o pedido de matrícula salvo
    erros = ''
    pedido_matricula = None
    id_diarios_salvos = []
    id_diarios_persistidos = []
    id_turma_persistida = None
    diarios_optativos_selecionados = []
    diarios_optativos_persistidos = []
    qs_pedido_matricula = ultima_matricula_periodo.pedidomatricula_set.filter(configuracao_pedido_matricula=configuracao_pedido_matricula_ativa)
    if qs_pedido_matricula:
        pedido_matricula = qs_pedido_matricula[0]
        id_turma_persistida = pedido_matricula.turma and pedido_matricula.turma.pk or None

        for item in pedido_matricula.pedidomatriculadiario_set.all().values_list('diario__id', flat=True):
            id_diarios_salvos.append(item)
            id_diarios_persistidos.append(item)
        diarios_optativos_persistidos = list(
            pedido_matricula.pedidomatriculadiario_set.filter(
                diario__componente_curricular__optativo=True,
            ).values_list(
                'diario__id',
                flat=True,
            )
        )

        # Exibição dos horários já salvos
        dias_semana = HorarioAulaDiario.DIA_SEMANA_CHOICES
        turnos = pedido_matricula.get_turnos_horarios()
        pedidos_diario_turma = pedido_matricula.pedidomatriculadiario_set.filter(diario__turma=pedido_matricula.turma)
        pedidos_diario_dependencias = pedido_matricula.pedidomatriculadiario_set.exclude(diario__turma=pedido_matricula.turma)

    if request.POST:
        for x in request.POST.getlist('diario'):
            diarios_optativos_selecionados.append(int(x))
        continuar = True

        # Validando se foi selecionada alguma turma caso seja a primeira chamada
        id_turma_selecionada = None
        if diarios_disponiveis_turma:
            if 'turma' not in request.POST:  # and not segunda_chamada:
                continuar = False
                erros += 'Você deve selecionar uma turma.'
            else:
                id_turma_selecionada = int(request.POST['turma'])

        if continuar:
            # TODO
            # Verificando se foi selecionado algum diário de cada disciplina em dependência
            if diarios_dependencia:
                componentes_id = diarios_dependencia.values_list('componente_curricular__componente_id', flat=True).distinct()
                for componente_id in componentes_id:
                    chaves = [f'diarios_{componente_id}']
                    for equivalente_id in Componente.get_ids_componentes_equivalentes(componente_id, aluno.matriz_id):
                        chaves.append(f'diarios_{equivalente_id}')
                    componente_selecionado = False
                    for chave in chaves:
                        if chave in request.POST:
                            componente_selecionado = True
                            break
                    if not componente_selecionado:
                        continuar = False
                        componente = Componente.objects.get(pk=componente_id)
                        erros += f'Escolha uma turma para a disciplina em dependência {componente.descricao_historico}.'
                    else:
                        id_diarios_salvos.append(int(request.POST[chave]))
                        #             else:
                        #                 if segunda_chamada and not id_turma_selecionada:
                        #                     continuar = False
                        #                     erros += u'Escolha ao menos uma turma ou uma disciplina em dependência para salvar o pedido.'

            # Selecionando a turma selecionada pelo aluno entre as turmas disponíveis para ele
            turma = None
            if diarios_disponiveis_turma:
                for turma_tmp in turmas:
                    if turma_tmp.pk == id_turma_selecionada:
                        turma = turma_tmp
                        break

            # validando choque de horário
            ids_validar_choque = list(ultima_matricula_periodo.matriculadiario_set.values_list('diario__id', flat=True))
            if turma:
                for diario in turma.diarios:
                    if not diario.componente_curricular.optativo or (
                        diario.componente_curricular.optativo and diario.pk in diarios_optativos_selecionados
                    ):
                        ids_validar_choque.append(diario.pk)

            # plano de retomada de aulas em virtude da pandemia (COVID19)
            if Diario.objects.filter(id__in=ids_validar_choque, turma__pertence_ao_plano_retomada=True).exists():
                diarios_com_choque = []
            else:
                diarios_com_choque = Diario.get_diarios_choque_horario(ids_validar_choque)
            if diarios_com_choque:
                continuar = False
                erros += 'Seu pedido não pôde ser salvo, pois há conflitos de horários entre as seguintes disciplinas:'

                for diario in diarios_com_choque:
                    erros += f'<br> - {diario.componente_curricular.componente} Horário: {diario.get_horario_aulas()}'

            # ------------------------------ 14/jul/2023 ----------------------------
            # alunos do técnico que estão devendo só a prática profissional com diário ofertado, são obrigados a se matricular no diário
            if aluno.curso_campus.modalidade.nivel_ensino_id == NivelEnsino.MEDIO:
                ids_diarios_pratica_profissional = []
                for turma_tmp in turmas:
                    for diario in turma_tmp.diarios:
                        if diario.componente_curricular.tipo == ComponenteCurricular.TIPO_PRATICA_PROFISSIONAL:
                            ids_diarios_pratica_profissional.append(diario.id)
                            break
                if (
                    ids_diarios_pratica_profissional
                    and aluno.pendencia_pratica_profissional
                    and not aluno.possui_pendencia(incluir_enade=False, incluir_colacao_grau=False, incluir_pratica_profissional=False)
                ):
                    matriculou_pratica_profissional = False
                    for id_diario_pratica_profissional in ids_diarios_pratica_profissional:
                        if (
                            id_diario_pratica_profissional in diarios_optativos_selecionados
                            or turma
                            and id_diario_pratica_profissional in list(turma.diarios.values_list('id', flat=True))
                        ):
                            matriculou_pratica_profissional = True
                            break
                    if not matriculou_pratica_profissional:
                        continuar = False
                        erros += 'Se matricule em um dos diários de prática profissional que estão sendo ofertados.'
            # ------------------------------------------------------------------------

            # verifica se diário optativo selecionado na turma também foi selecionado na listagem de diários pendentes
            if diarios_dependencia and diarios_optativos_selecionados:
                for diario in (
                    Diario.objects.filter(id__in=diarios_optativos_selecionados)
                    .select_related('componente_curricular__componente')
                    .only('id', 'componente_curricular__componente__id', 'componente_curricular__componente__sigla')
                ):
                    if diario.componente_curricular.componente.id in componentes_id:
                        diario_selecionado_id = request.POST.get(f'diarios_{diario.componente_curricular.componente.id}')
                        if diario_selecionado_id and diario.id != int(diario_selecionado_id):
                            continuar = False
                            erros += (
                                f'O componente curricular {diario.componente_curricular.componente.sigla} não pode ser selecionado mais de uma vez. '
                            )

            # caso exista algum erro e já exista um pedido de matrícula salvo, será exibido os pedidos salvos
            if pedido_matricula and not continuar:
                id_diarios_salvos = id_diarios_persistidos
                id_turma_selecionada = id_turma_persistida

            if continuar:
                # salvando o pedido de mnatricula
                if pedido_matricula:
                    pedido_matricula.pedidomatriculadiario_set.all().delete()
                else:
                    pedido_matricula = PedidoMatricula()
                pedido_matricula.matricula_periodo = ultima_matricula_periodo
                pedido_matricula.configuracao_pedido_matricula = configuracao_pedido_matricula_ativa
                if diarios_disponiveis_turma:
                    pedido_matricula.turma = turma
                pedido_matricula.save()

                # salvando os pedidos de matrícula nos diários disponíveis para aluno da turma selecionada por ele
                if turma:
                    for diario in turma.diarios:
                        if not diario.componente_curricular.optativo or diario.pk in diarios_optativos_selecionados:
                            pedido_matricula_diario = PedidoMatriculaDiario()
                            pedido_matricula_diario.diario = diario
                            pedido_matricula_diario.pedido_matricula = pedido_matricula
                            pedido_matricula_diario.save()

                # salvando os pedidos de matrícula nos diários das disciplinas pendentes
                if diarios_dependencia:
                    for componente_id in componentes_id:
                        diario = Diario.objects.get(pk=request.POST.get(f'diarios_{componente_id}'))
                        pedido_matricula_diario = PedidoMatriculaDiario()
                        pedido_matricula_diario.diario = diario
                        pedido_matricula_diario.pedido_matricula = pedido_matricula
                        pedido_matricula_diario.save()

                if diarios_dependencia or diarios_disponiveis_turma:
                    return httprr('.', 'Pedido de matrícula salvo com sucesso.')
                else:
                    return httprr('.', 'Pedido de manutenção do vínculo com a instituição salvo com sucesso.')

    return locals()


@rtr()
@login_required()
def pedido_matricula_credito(request, aluno_pk):
    aluno = get_object_or_404(Aluno.locals, pk=aluno_pk)

    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, aluno.curso_campus)
    if not pode_realizar_procedimentos and not aluno.is_user(request):
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    if not aluno.pode_matricula_online() or aluno.is_seriado() or aluno.is_modular():
        return httprr('/', 'Não existe um período de renovação de matrícula ativa para o seu curso.', 'error')

    configuracao_pedido_matricula_ativa = aluno.get_configuracao_pedido_matricula_ativa()
    if aluno.is_user(request) and configuracao_pedido_matricula_ativa.requer_atualizacao_dados and 'dados_atualizados' not in request.session:
        return httprr(f'/edu/atualizar_meus_dados_pessoais/{aluno.matricula}/1/')

    if (
        aluno.is_user(request)
        and configuracao_pedido_matricula_ativa.requer_atualizacao_caracterizacao
        and 'caracterizacao_atualizada' not in request.session
    ):
        return httprr(f'/ae/caracterizacao/{aluno.pk}/1/')

    permite_quebrar_requisitos = configuracao_pedido_matricula_ativa.permite_requerimento_quebra_de_requisito
    permite_requerer_aumento_ch = configuracao_pedido_matricula_ativa.permite_requerimento_ultrapassar_ch_maxima
    data_limite_requerimentos_especiais = configuracao_pedido_matricula_ativa.data_limite_requerimentos_especiais

    ultima_matricula_periodo = aluno.get_ultima_matricula_periodo()
    segunda_chamada = ultima_matricula_periodo.situacao_id in [
        SituacaoMatriculaPeriodo.MATRICULA_VINCULO_INSTITUCIONAL,
        SituacaoMatriculaPeriodo.MATRICULADO,
    ]
    title = 'Matrícula Online ({})'.format(segunda_chamada and '2ª Chamada' or '1ª Chamada')
    deve_impedir_matricula_vinculo = aluno.deve_impedir_matricula_vinculo()

    # Recuperando diários das disciplinas obrigatórias disponíveis
    diarios_obrigatorias = aluno.get_diarios_pendentes_matricula_online(apenas_obrigatorias=True)
    ids_disciplinas_obrigatorias = diarios_obrigatorias.values_list('componente_curricular__componente_id', flat=True).distinct()

    # Recuperando diários das disciplinas optativas disponíveis
    diarios_optativas = aluno.get_diarios_pendentes_matricula_online(
        apenas_optativas=True, ids_componentes_diarios_obrigatorias=ids_disciplinas_obrigatorias
    )

    # Recuperando diários das disciplinas eletivas disponíveis
    if aluno.matriz.ch_componentes_eletivos > 0 or configuracao_pedido_matricula_ativa.permite_solicitacao_disciplinas_eletivas:
        diarios_eletivas = aluno.get_diarios_eletivas_matricula_online(
            configuracao_pedido_matricula_ativa.restringir_disciplinas_eletivas_mesmo_curso
        )

    # Recuperando diários que o aluno já se matrículou neste período
    diarios_matriculados = ultima_matricula_periodo.get_matriculas_diario().exclude(situacao=MatriculaDiario.SITUACAO_CANCELADO)
    ids_diarios_matriculados = diarios_matriculados.values_list('diario_id', flat=True).distinct()

    # Recuperando pedido de matrícula já salvo no atual período de pedido de matrícula
    pedido_matricula = None
    erros = ''

    id_diarios_salvos = []
    id_diarios_persistidos = []
    id_diarios_cancelados = []
    qs_pedido_matricula = ultima_matricula_periodo.pedidomatricula_set.filter(configuracao_pedido_matricula=configuracao_pedido_matricula_ativa)
    if qs_pedido_matricula:
        pedido_matricula = qs_pedido_matricula[0]
        for item in pedido_matricula.pedidomatriculadiario_set.all().values_list('diario__id', flat=True):
            id_diarios_salvos.append(item)
            id_diarios_persistidos.append(item)

        # Variáveis para exibição do quadro de horários
        dias_semana = HorarioAulaDiario.get_dias_semana_seg_a_sex()
        turnos = pedido_matricula.get_turnos_horarios()
        pedidos_diario_dependencias = pedido_matricula.pedidomatriculadiario_set.all()
        id_diarios_cancelados = pedido_matricula.matriculas_diario_canceladas.values_list('id', flat=True)

    if permite_requerer_aumento_ch and pedido_matricula:
        ids_componentes_pedidos_via_requerimento = pedido_matricula.requerimentos_matricula_com_aumento_ch.filter(deferido=True).values_list(
            'diario__componente_curricular__componente_id', flat=True
        )
        if ids_componentes_pedidos_via_requerimento:
            diarios_obrigatorias = diarios_obrigatorias.exclude(componente_curricular__componente_id__in=ids_componentes_pedidos_via_requerimento)
            diarios_optativas = diarios_optativas.exclude(componente_curricular__componente_id__in=ids_componentes_pedidos_via_requerimento)
            if 'diarios_eletivas' in locals():
                diarios_eletivas = diarios_eletivas.exclude(componente_curricular__componente_id__in=ids_componentes_pedidos_via_requerimento)

    # requerimentos de disciplinas extracurriculares
    ids_diarios_requeridos = pedido_matricula.requerimentos_matricula_disciplina.values_list('diario', flat=True) if pedido_matricula else []
    qs_diarios_requerimento = Diario.objects
    if 'requerimento' in request.GET:
        RequerimentoMatriculaDisciplina.objects.filter(aluno=aluno, pk=request.GET['requerimento']).delete()
        return httprr(request.path, 'Solicitação excluída com sucesso.')
    if 'requerer' in request.GET:
        ids_diarios_validar_choque = list(ids_diarios_matriculados)
        ids_diarios_validar_choque.append(int(request.GET['requerer']))
        diarios_com_choque = Diario.get_diarios_choque_horario(ids_diarios_validar_choque)
        if diarios_com_choque:
            erros += 'Seu requerimento não pôde ser salvo, pois há conflitos de horários entre as seguintes disciplinas:'
            for diario in diarios_com_choque:
                erros += f'<br> - {diario.componente_curricular.componente} Horário: {diario.get_horario_aulas()}'
        else:
            requerimento = RequerimentoMatriculaDisciplina.objects.create(
                aluno=aluno, tipo=Requerimento.MATRICULA_DISCIPLINA, data=datetime.date.today(), diario_id=request.GET['requerer']
            )
            if pedido_matricula is None:
                pedido_matricula = PedidoMatricula()
                pedido_matricula.matricula_periodo = ultima_matricula_periodo
                pedido_matricula.configuracao_pedido_matricula = configuracao_pedido_matricula_ativa
                pedido_matricula.save()
            pedido_matricula.requerimentos_matricula_disciplina.add(requerimento)
            return httprr(request.path, 'Disciplina requerida com sucesso.')
    if 'disciplina' in request.GET:
        qs_diarios_requerimento = qs_diarios_requerimento.filter(
            turma__ano_letivo=ultima_matricula_periodo.ano_letivo,
            turma__periodo_letivo=ultima_matricula_periodo.periodo_letivo,
            turma__curso_campus__diretoria=aluno.curso_campus.diretoria,
        ).filter(componente_curricular__componente__descricao__icontains=request.GET['disciplina'])
        if configuracao_pedido_matricula_ativa.restringir_disciplinas_eletivas_mesmo_curso:
            qs_diarios_requerimento = qs_diarios_requerimento.filter(turma__curso_campus_id=aluno.curso_campus_id)
    else:
        qs_diarios_requerimento = qs_diarios_requerimento.none()
    diarios_requerimento = []
    for diario_requerimento in qs_diarios_requerimento:
        if diario_requerimento.get_qtd_vagas_restante():
            diarios_requerimento.append(diario_requerimento)

    # quantitativos para validação
    estrutura = aluno.matriz.estrutura
    ids_disciplinas_optativas = diarios_optativas.values_list('componente_curricular__componente_id', flat=True).order_by().distinct()
    qtd_disciplinas_obrigatorias = ids_disciplinas_obrigatorias.count()
    qtd_disciplinas_optativas = ids_disciplinas_optativas.count()
    qtd_disciplinas_matriculadas = ids_diarios_matriculados.count()
    qtd_disciplinas_matriz_disponiveis = qtd_disciplinas_obrigatorias + qtd_disciplinas_optativas + qtd_disciplinas_matriculadas
    qtd_componentes_obrigatorios_matriz_periodo_atual = len(aluno.matriz.get_ids_componentes(periodos=[aluno.periodo_atual], apenas_obrigatorio=True))
    qtd_disciplinas_pendentes = diarios_obrigatorias.count()

    if estrutura.numero_disciplinas_superior_periodo:
        qtd_maxima_disciplinas = qtd_componentes_obrigatorios_matriz_periodo_atual + estrutura.numero_disciplinas_superior_periodo

    qtd_minima_disciplinas = estrutura.qtd_minima_disciplinas or 0
    if qtd_minima_disciplinas:
        diarios_abaixo_qtd_minima = 0 < qtd_disciplinas_matriz_disponiveis <= qtd_minima_disciplinas
        diarios_acima_qtd_minima = qtd_disciplinas_matriz_disponiveis > qtd_minima_disciplinas

    if permite_quebrar_requisitos:
        if 'requerimento_qr' in request.GET:
            requerimento_id = request.GET['requerimento_qr']
            requerimento = RequerimentoMatriculaQuebraRequisito.objects.filter(aluno=aluno, pk=requerimento_id).first()

            if not requerimento:
                return httprr(request.path, 'Requerimento não encontrado.', 'error')

            deferido = requerimento.deferido
            if deferido is False:
                return httprr(request.path, 'Você não tem permissão para cancelar um requerimento indeferido.', 'error')

            if deferido is True:
                PedidoMatriculaDiario.objects.filter(
                    pedido_matricula__requerimentos_matricula_quebra_de_requisito=requerimento, diario=requerimento.diario
                ).delete()
            requerimento.delete()
            return httprr(request.path, 'Requerimento e pedido de matrícula cancelados com sucesso.')

        ids_componentes_cursados = list(aluno.get_ids_componentes_cursando()) + list(aluno.get_ids_componentes_cumpridos())
        componentes_pendentes = ComponenteCurricular.objects.filter(matriz=aluno.matriz).exclude(componente_id__in=ids_componentes_cursados)
        ids_componentes_com_requisitos_nao_cumpridos = []
        for cc in componentes_pendentes:
            if cc.pre_requisitos.count() > cc.pre_requisitos.filter(componente_id__in=ids_componentes_cursados).distinct().count():
                ids_componentes_com_requisitos_nao_cumpridos.append(cc.componente_id)
            if cc.co_requisitos.count() > cc.co_requisitos.filter(componente_id__in=ids_componentes_cursados).count():
                ids_componentes_com_requisitos_nao_cumpridos.append(cc.componente_id)

        ids_diarios_pedidos_matricula = pedido_matricula.pedidomatriculadiario_set.values_list('diario_id', flat=True) if pedido_matricula else []
        ids_diarios_com_requerimento_vigente_ou_indeferido = (
            RequerimentoMatriculaQuebraRequisito.objects.filter(aluno=aluno).exclude(deferido=True).values_list('diario_id', flat=True)
        )
        diarios_passiveis_de_quebra_requisito = (
            Diario.objects.select_related('turma', 'componente_curricular')
            .filter(
                turma__ano_letivo=ultima_matricula_periodo.ano_letivo,
                turma__periodo_letivo=ultima_matricula_periodo.periodo_letivo,
                componente_curricular__componente_id__in=ids_componentes_com_requisitos_nao_cumpridos,
            )
            .exclude(pk__in=list(ids_diarios_pedidos_matricula) + list(ids_diarios_com_requerimento_vigente_ou_indeferido))
            .order_by('-componente_curricular__optativo', 'componente_curricular__componente__descricao')
        )
        if configuracao_pedido_matricula_ativa.restringir_por_curso:
            diarios_passiveis_de_quebra_requisito = diarios_passiveis_de_quebra_requisito.filter(
                turma__curso_campus=aluno.curso_campus,
            )

        pode_requerer_quebra = datetime.date.today() <= data_limite_requerimentos_especiais
        requerimentos_quebra_requisito = pedido_matricula.requerimentos_matricula_quebra_de_requisito if pedido_matricula else None

    if permite_requerer_aumento_ch and estrutura.ch_maxima_disciplinas:
        if 'requerimento_aumento_ch' in request.GET:
            requerimento_id = request.GET['requerimento_aumento_ch']
            requerimento = RequerimentoMatriculaComAumentoDeCH.objects.filter(aluno=aluno, pk=requerimento_id).first()

            if not requerimento:
                return httprr(request.path, 'Requerimento não encontrado.', 'error')

            deferido = requerimento.deferido
            if deferido is False:
                return httprr(request.path, 'Você não tem permissão para cancelar um requerimento indeferido.', 'error')

            if deferido is True:
                PedidoMatriculaDiario.objects.filter(
                    pedido_matricula__requerimentos_matricula_com_aumento_ch=requerimento, diario=requerimento.diario
                ).delete()
            requerimento.delete()
            return httprr(request.path, 'Requerimento e pedido de matrícula cancelados com sucesso.')

        ch_total = pedido_matricula.carga_horaria_total if pedido_matricula else 0

        ids_componentes_pedidos_matricula = (
            list(pedido_matricula.pedidomatriculadiario_set.values_list('diario__componente_curricular__componente_id', flat=True))
            if pedido_matricula
            else []
        )
        ids_componentes_requerimentos = (
            (
                list(
                    pedido_matricula.requerimentos_matricula_quebra_de_requisito.values_list(
                        'diario__componente_curricular__componente_id', flat=True
                    )
                )
                + list(pedido_matricula.requerimentos_matricula_com_aumento_ch.values_list('diario__componente_curricular__componente_id', flat=True))
            )
            if pedido_matricula
            else []
        )
        diarios_com_ch_resultante = (
            aluno.get_diarios_pendentes_matricula_online()
            .only('pk', 'componente_curricular__componente_id', 'componente_curricular__componente__ch_hora_relogio')
            .exclude(componente_curricular__componente_id__in=set(ids_componentes_pedidos_matricula + ids_componentes_requerimentos))
            .annotate(ch_resultante=F('componente_curricular__componente__ch_hora_relogio') + ch_total)
        )

        diarios_passiveis_de_aumento_ch = (
            configuracao_pedido_matricula_ativa.get_diarios()
            .select_related('componente_curricular__componente')
            .filter(pk__in=diarios_com_ch_resultante.filter(ch_resultante__gt=estrutura.ch_maxima_disciplinas).values_list('pk', flat=True))
        )
        pode_requerer_aumento_ch = datetime.date.today() <= data_limite_requerimentos_especiais
        requerimentos_aumento_ch = pedido_matricula.requerimentos_matricula_com_aumento_ch

    if request.POST:
        continuar = True
        diarios_solicitados = []
        ids_disciplinas_solicitadas = []
        componente_diario = {}
        ch_solicitadas = 0
        for chave in list(request.POST.keys()):
            if 'diario' in chave:
                diario = Diario.objects.filter(pk=request.POST.get(chave)).first()
                if diario:
                    diarios_solicitados.append(diario)
                    id_diarios_salvos.append(int(request.POST[chave]))
                    ids_disciplinas_solicitadas.append(diario.componente_curricular.componente.id)
                    componente_diario[diario.componente_curricular.componente.id] = diario
                    if estrutura.ch_minima_disciplinas or estrutura.ch_maxima_disciplinas:
                        ch_solicitadas += diario.componente_curricular.componente.get_ch_hora_relogio()

        if ids_disciplinas_solicitadas:
            ids_cursando = aluno.get_ids_componentes_cursando()
            ids_cumprido = aluno.get_ids_componentes_cumpridos()
            for componente in ids_disciplinas_solicitadas:
                ids_correquisitos = componente_diario[componente].componente_curricular.get_corequisitos()
                for correquisito in ids_correquisitos:
                    if correquisito not in ids_cursando and correquisito not in ids_cumprido and correquisito not in ids_disciplinas_solicitadas:
                        continuar = False
                        componente_correquisito = Componente.objects.get(id=correquisito)
                        componente_pendente = Componente.objects.get(id=componente)
                        erros += f'A disciplina {componente_pendente} possui co requisito pendente ({componente_correquisito}).'

        # adiciona pedidos oriundos de requerimentos à lista de disciplinas solicitadas
        if pedido_matricula:
            ids_disciplinas_solicitadas.extend(
                pedido_matricula.requerimentos_matricula_quebra_de_requisito.values_list('diario__componente_curricular__componente_id', flat=True)
            )
            ids_disciplinas_solicitadas.extend(
                pedido_matricula.requerimentos_matricula_com_aumento_ch.values_list('diario__componente_curricular__componente_id', flat=True)
            )

        qtd_disciplinas_solicitadas = len(ids_disciplinas_solicitadas)

        # se ele já realizou um pedido e foi deferido, ele deve escolher ao menos um diário na segunda chamada se tiver menos disciplinas que o exigido na estrutura
        if (
            segunda_chamada
            and (qtd_disciplinas_obrigatorias + qtd_disciplinas_optativas) > 0
            and not ids_disciplinas_solicitadas
            and qtd_disciplinas_matriculadas < qtd_minima_disciplinas
        ):
            continuar = False
            erros += 'É necessário escolher, ao menos, uma disciplina na segunda chamada.'

        # validar ch_minima_disciplinas e ch_maxima_disciplinas
        ch_minima_disciplinas = estrutura.ch_minima_disciplinas or 0
        ch_maxima_disciplinas = estrutura.ch_maxima_disciplinas or 0
        if ch_minima_disciplinas or ch_maxima_disciplinas:
            ch_diarios_matriculados = mask_ch_componente(
                diarios_matriculados.distinct().aggregate(qtd=Sum('diario__componente_curricular__componente__ch_hora_relogio')).get('qtd') or 0
            )
            ch_diarios_solicitados_por_requerimento = (
                mask_ch_componente(
                    # *Para fins de validação de carga horária máxima*, diários solicitados via
                    # requerimento de aumento de CH são ignorados.
                    pedido_matricula.requerimentos_matricula_quebra_de_requisito.filter(deferido=True)
                    .aggregate(ch_total=Sum('diario__componente_curricular__componente__ch_hora_relogio'))
                    .get('ch_total')
                    or 0
                )
                if pedido_matricula
                else 0
            )
            ch_pedido_total = ch_solicitadas + ch_diarios_solicitados_por_requerimento + ch_diarios_matriculados
            if ch_minima_disciplinas:
                ch_diarios_obrigatorias = mask_ch_componente(
                    diarios_obrigatorias.distinct().aggregate(qtd=Sum('componente_curricular__componente__ch_hora_relogio')).get('qtd') or 0
                )
                ch_diarios_optativas = mask_ch_componente(
                    diarios_optativas.distinct().aggregate(qtd=Sum('componente_curricular__componente__ch_hora_relogio')).get('qtd') or 0
                )
                ch_disciplinas_matriz_disponiveis = ch_diarios_matriculados + ch_diarios_obrigatorias + ch_diarios_optativas

                # se existe ch disponível para solicitar e o pedido não atingiu a carga horária mínima
                if ch_disciplinas_matriz_disponiveis >= ch_minima_disciplinas and ch_pedido_total < ch_minima_disciplinas:
                    continuar = False
                    erros += f'A carga horária mínima de {ch_minima_disciplinas} horas em disciplinas não foi atingida.'

            if ch_maxima_disciplinas and ch_pedido_total > ch_maxima_disciplinas:
                continuar = False
                erros += f'A carga horária máxima de {ch_maxima_disciplinas} horas em disciplinas foi ultrapassada.'

        # validando se a quantidade de diários disponíveis está abaixo da qtd mínima de disciplinas da estrutura do curso
        # ou seja, será necessário escolher todas as disciplinas obrigatórias e optativas disponíveis
        if qtd_disciplinas_pendentes > qtd_minima_disciplinas and qtd_minima_disciplinas and diarios_abaixo_qtd_minima:
            if not request.user.has_perm('edu.pode_quebrar_quantidade_minima'):
                for componente_oo in ids_disciplinas_obrigatorias:
                    if componente_oo not in ids_disciplinas_solicitadas:
                        continuar = False

                if not continuar:
                    erros += 'Você deve selecionar todas as disciplinas obrigatórias.'

        # validando a quantidade mínima de disciplinas
        elif (
            qtd_minima_disciplinas
            and diarios_acima_qtd_minima
            and (qtd_disciplinas_solicitadas + qtd_disciplinas_matriculadas < qtd_minima_disciplinas)
        ):
            if not request.user.has_perm('edu.pode_quebrar_quantidade_minima'):
                # se o aluno necessita pagar mais do que a quantidade mínima de disciplina informada na estrutura do curso
                if qtd_disciplinas_pendentes > qtd_minima_disciplinas:
                    continuar = False
                    if qtd_disciplinas_matriculadas > 0:
                        erros += f'Escolha, no mínimo, {qtd_minima_disciplinas - qtd_disciplinas_matriculadas} disciplina(s) obrigatória(s) e/ou optativa(s).'
                    else:
                        erros += f'Escolha, no mínimo, {qtd_minima_disciplinas} disciplina(s) obrigatória(s) e/ou optativa(s) para cursar no próximo período letivo.'
                # o aluno está precisando cursar menos disciplinas do que a quantidade mínima de disciplina informada na estrutura do curso, logo ele deve escolher todas as disciplinas obrigatórias
                else:
                    for componente_oo in ids_disciplinas_obrigatorias:
                        if componente_oo not in ids_disciplinas_solicitadas:
                            continuar = False
                    if not continuar:
                        erros += 'Você deve selecionar todas as disciplinas obrigatórias.'

        # validando a quantidade de disciplinas que podem ser cursadas a mais da quantidade de disciplinas do seu período atual
        elif estrutura.numero_disciplinas_superior_periodo and qtd_disciplinas_solicitadas + qtd_disciplinas_matriculadas > qtd_maxima_disciplinas:
            continuar = False

            if qtd_disciplinas_matriculadas > 0:
                erros += f'Não é permitido se matricular em mais de {qtd_maxima_disciplinas} disciplinas por período. Ainda é possível se matricular em {qtd_maxima_disciplinas - qtd_disciplinas_matriculadas} disciplinas.'
            else:
                erros += f'Não é permitido se matricular em mais de {qtd_maxima_disciplinas} disciplinas por período.'
        else:
            # validando choque de horário
            ids_diarios_validar_choque = []
            # inserindo os diarios já matriculados
            ids_diarios_cancelar = (
                MatriculaDiario.objects.filter(id__in=request.POST.getlist('cancelar_md')).values_list('diario', flat=True)
                if request.POST and 'cancelar_md' in request.POST
                else []
            )
            for id_diarios_matriculados in ids_diarios_matriculados:
                if id_diarios_matriculados not in ids_diarios_cancelar:
                    ids_diarios_validar_choque.append(id_diarios_matriculados)
            # inserindo os diarios solicitados
            for diario_solicitado in diarios_solicitados:
                ids_diarios_validar_choque.append(diario_solicitado.id)
            if Diario.objects.filter(id__in=ids_diarios_validar_choque, turma__pertence_ao_plano_retomada=True).exists():
                diarios_com_choque = []
            else:
                diarios_com_choque = Diario.get_diarios_choque_horario(ids_diarios_validar_choque)
            if diarios_com_choque:
                continuar = False
                erros += 'Seu pedido não pôde ser salvo, pois há conflitos de horários entre as seguintes disciplinas:'

                for diario in diarios_com_choque:
                    erros += f'<br> - {diario.componente_curricular.componente} Horário: {diario.get_horario_aulas()}'

        # caso exista algum erro e já exista um pedido de matrícula salvo, será exibido os pedidos salvos
        if pedido_matricula and not continuar:
            id_diarios_salvos = id_diarios_persistidos

        if pedido_matricula and continuar:
            if configuracao_pedido_matricula_ativa.permite_cancelamento_matricula_diario:
                pedido_matricula.matriculas_diario_canceladas.clear()
                ids_cancelar_md = request.POST.getlist('cancelar_md')
                for md in MatriculaDiario.objects.filter(id__in=ids_cancelar_md):
                    try:
                        md.cancelar(False)
                        pedido_matricula.matriculas_diario_canceladas.add(md)
                    except ValidationError as e:
                        continuar = False
                        erros += f'Seu pedido não pôde ser salvo, pois não é possível cancelar a matrícula no diário {md.diario}. Motivo: {e.message}'

        if continuar:
            # salvando o pedido de matrícula
            if pedido_matricula:
                ids_pedidos_gerados_por_requerimento = set(
                    list(pedido_matricula.requerimentos_matricula_quebra_de_requisito.filter(deferido=True).values_list('diario_id', flat=True))
                    + list(pedido_matricula.requerimentos_matricula_com_aumento_ch.filter(deferido=True).values_list('diario_id', flat=True))
                )
                pedido_matricula.pedidomatriculadiario_set.exclude(diario_id__in=ids_pedidos_gerados_por_requerimento).delete()
            else:
                pedido_matricula = PedidoMatricula()
            pedido_matricula.matricula_periodo = ultima_matricula_periodo
            pedido_matricula.configuracao_pedido_matricula = configuracao_pedido_matricula_ativa
            pedido_matricula.save()

            # salvando os pedidos de matrícula em diário
            for diario in diarios_solicitados:
                pedido_matricula_diario = PedidoMatriculaDiario()
                pedido_matricula_diario.diario = diario
                pedido_matricula_diario.pedido_matricula = pedido_matricula
                pedido_matricula_diario.save()

            if qtd_disciplinas_solicitadas:
                return httprr('.', 'Pedidos de matrícula salvos com sucesso.')
            else:
                return httprr('.', 'Pedido de manutenção do vínculo com a instituição salvo com sucesso.')

    # caso o usuário seja o próprio aluno, sua estrutura possibilizar plano de estudo e ele já tenha atingido
    # o tempo mínimo para conclusão do curso, ele poderá informar se deseja a criação de um plano de estudo
    pode_solicitar_plano_estudo = (
        aluno.is_user(request) and estrutura.plano_estudo and aluno.matriculaperiodo_set.count() > aluno.matriz.qtd_periodos_letivos
    )
    if 'plano_estudo' in request.GET:
        pedido_matricula = PedidoMatricula()
        pedido_matricula.matricula_periodo = ultima_matricula_periodo
        pedido_matricula.configuracao_pedido_matricula = configuracao_pedido_matricula_ativa
        pedido_matricula.save()
        plano_estudo = PlanoEstudo()
        plano_estudo.tipo = 'Planejamento'
        plano_estudo.pedido_matricula = pedido_matricula
        plano_estudo.save()
        return httprr(f'/edu/pedido_matricula_credito/{aluno.pk}/', 'Solicitação de plano de estudo realizada com sucesso.')
    solicitou_dispensa_plano_estudo = False
    solicitou_criacao_plano_estudo = False
    if pode_solicitar_plano_estudo and pedido_matricula:
        solicitou_criacao_plano_estudo = pedido_matricula.planoestudo_set.filter(tipo='Planejamento').exists()
        solicitou_dispensa_plano_estudo = pedido_matricula.planoestudo_set.filter(tipo='Dispensa').exists()
        if not solicitou_criacao_plano_estudo and not solicitou_dispensa_plano_estudo:
            plano_estudo = PlanoEstudo()
            plano_estudo.tipo = 'Dispensa'
            plano_estudo.pedido_matricula = pedido_matricula
            plano_estudo.save()
            solicitou_dispensa_plano_estudo = True
    return locals()


@rtr()
@login_required()
def requerer_quebra_requisito(request, aluno_pk, diario_pk):
    aluno = get_object_or_404(Aluno, pk=aluno_pk)
    diario = get_object_or_404(Diario, pk=diario_pk)
    title = f'Requerer quebra de requisitos para "{diario.componente_curricular}"'
    redirecionar = request.GET.get('redirecionar')
    if not aluno.pode_matricula_online() or aluno.is_seriado() or aluno.is_modular():
        return httprr(redirecionar or '..', 'Não existe um período de renovação de matrícula ativa para o seu curso.', 'error', close_popup=True)
    configuracao_pedido_matricula_ativa = aluno.get_configuracao_pedido_matricula_ativa()
    if not configuracao_pedido_matricula_ativa.get_diarios().filter(pk=diario_pk).exists():
        return httprr(redirecionar or '..', 'O diário selecionado não está disponível para matrícula.', 'error', close_popup=True)

    pedido_indeferido = Requerimento.objects.filter(aluno=aluno, diario=diario, tipo=Requerimento.MATRICULA_QUEBRA_REQUISITO, deferido=False).exists()

    if pedido_indeferido:
        return httprr(
            redirecionar or '..', 'Você possui um pedido indeferido para esta disciplina. Novo requerimento não permitido.', 'error', close_popup=True
        )

    form = RequerimentoQuebraRequisitoForm(data=request.POST or None, files=request.FILES or None)

    if form.is_valid():
        with transaction.atomic():
            form.instance.aluno = aluno
            form.instance.diario = diario
            form.instance.data = datetime.date.today()
            requerimento = form.save()

            ultima_matricula_periodo = aluno.get_ultima_matricula_periodo()
            pedido_matricula = ultima_matricula_periodo.pedidomatricula_set.filter(
                configuracao_pedido_matricula=configuracao_pedido_matricula_ativa
            ).first()
            if pedido_matricula is None:
                pedido_matricula = PedidoMatricula.objects.create(
                    matricula_periodo=ultima_matricula_periodo, configuracao_pedido_matricula=configuracao_pedido_matricula_ativa
                )
            pedido_matricula.requerimentos_matricula_quebra_de_requisito.add(requerimento)

        return httprr('..', 'Requerimento cadastrado com sucesso.')
    return locals()


@rtr()
@login_required()
def requerer_matricula_com_aumento_ch(request, aluno_pk, diario_pk):
    aluno = get_object_or_404(Aluno, pk=aluno_pk)
    diario = get_object_or_404(Diario, pk=diario_pk)
    title = f'Requerer aumento de CH para matrícula em "{diario.componente_curricular}"'
    redirecionar = request.GET.get('redirecionar')
    if not aluno.pode_matricula_online() or aluno.is_seriado() or aluno.is_modular():
        return httprr(redirecionar or '..', 'Não existe um período de renovação de matrícula ativa para o seu curso.', 'error', close_popup=True)
    configuracao_pedido_matricula_ativa = aluno.get_configuracao_pedido_matricula_ativa()
    if not configuracao_pedido_matricula_ativa.get_diarios().filter(pk=diario_pk).exists():
        return httprr(redirecionar or '..', 'O diário selecionado não está disponível para matrícula.', 'error', close_popup=True)

    pedido_indeferido = RequerimentoMatriculaComAumentoDeCH.objects.filter(aluno=aluno, diario=diario, deferido=False).exists()

    if pedido_indeferido:
        return httprr(
            redirecionar or '..', 'Você possui um pedido indeferido para esta disciplina. Novo requerimento não permitido.', 'error', close_popup=True
        )

    ultima_matricula_periodo = aluno.get_ultima_matricula_periodo()
    pedido_matricula = ultima_matricula_periodo.pedidomatricula_set.filter(configuracao_pedido_matricula=configuracao_pedido_matricula_ativa).first()

    estrutura = aluno.matriz.estrutura
    ch_total = pedido_matricula.carga_horaria_total if pedido_matricula else 0

    form = RequerimentoMatriculaComAumentoCHForm(data=request.POST or None, files=request.FILES or None)

    if form.is_valid():
        with transaction.atomic():
            form.instance.aluno = aluno
            form.instance.diario = diario
            form.instance.data = datetime.date.today()
            requerimento = form.save()

            if pedido_matricula is None:
                pedido_matricula = PedidoMatricula.objects.create(
                    matricula_periodo=ultima_matricula_periodo, configuracao_pedido_matricula=configuracao_pedido_matricula_ativa
                )
            pedido_matricula.requerimentos_matricula_com_aumento_ch.add(requerimento)

        return httprr('..', 'Requerimento cadastrado com sucesso.')
    return locals()


@rtr('admin/indeferir_em_lote.html')
@permission_required('edu.pode_indeferir_em_lote')
def indeferir_em_lote(request: HttpRequest) -> HttpResponse | dict:
    title = 'Indeferir requerimentos em lote'
    queryset = Requerimento.objects.filter(id__in=ids_da_query(request))

    try:
        Requerimento.validar_tipos_na_avaliacao_em_lote(queryset)
    except ValidationError as err:
        return httprr(reverse('admin:edu_requerimento_changelist'), message=f'{err.message}', tag='error')

    form = IndeferirRequerimentoEmLoteForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            observacao = form.cleaned_data['observacao']
            processados = 0
            ignorados = []

            for requerimento in queryset:
                if requerimento.deferido is None:
                    requerimento.observacao = observacao
                    requerimento.indeferir(request.user)
                    processados += 1
                else:
                    ignorados.append(f'#{requerimento.pk}')

            mensagem_sucesso = ''
            if processados:
                mensagem_sucesso = f'{processados} requerimento(s) indeferido(s) com sucesso.'

            if ignorados:
                mensagem_sucesso += (
                    f'{mensagem_sucesso} Os seguintes requerimentos já haviam sido avaliados e foram ignorados: {", ".join(ignorados)}'.strip()
                )

            if mensagem_sucesso:
                messages.success(request, mensagem_sucesso)

            return httprr(reverse('admin:edu_requerimento_changelist'))

    return locals()


@permission_required('edu.add_configuracaopedidomatricula')
@rtr()
def add_curso_configuracao_pedido_matricula(request, pk):
    title = 'Informar Cursos'
    obj = get_object_or_404(ConfiguracaoPedidoMatricula, pk=pk)
    if not obj.pode_ser_alterado():
        return httprr('..', 'O pedido não pode ser alterado.', 'error')

    form = AddCursoConfiguracaoPedidoMatriculaForm(request=request, data=request.POST or None, instance=obj)
    if form.is_valid():
        form.save()
        return httprr('..', 'Curso(s) adicionado(s) com sucesso.')
    return locals()


@permission_required('edu.view_configuracaopedidomatricula')
@rtr()
def configuracao_pedido_matricula(request, pk):
    title = 'Renovação de Matrícula'
    obj = get_object_or_404(ConfiguracaoPedidoMatricula, pk=pk)
    NOTA_DECIMAL = settings.NOTA_DECIMAL

    cancelar = request.GET.get('cancelar')
    if cancelar and request.user.has_perm('edu.change_configuracaopedidomatricula'):
        if int(cancelar):
            if not obj.is_processado():
                try:
                    obj.cancelar()
                    return httprr('.', 'Cancelamento realizado com sucesso.')
                except ValidationError as e:
                    return httprr('.', f'Não foi possível cancelar a renovação de matrícula: {e.messages[0]}', 'error')
        else:
            if obj.is_cancelado():
                obj.desfazer_cancelamento()
                return httprr('.', 'Cancelamento desfeito com sucesso.')

    turmas = None
    curso_escolhido = None
    turma_escolhida = None
    tab = request.GET.get('tab')
    if tab == 'monitoramento' or tab == 'pendencias':
        if request.GET.get('curso'):
            curso_escolhido = get_object_or_404(CursoCampus, pk=request.GET.get('curso'))
            qs_diarios = obj.get_diarios()
            qs_diarios_com_pratica_profissional = qs_diarios.filter(
                componente_curricular__tipo__in=[
                    ComponenteCurricular.TIPO_PRATICA_PROFISSIONAL,
                    ComponenteCurricular.TIPO_TRABALHO_CONCLUSAO_CURSO,
                    ComponenteCurricular.TIPO_SEMINARIO,
                ]
            )
            qs_diarios = (
                qs_diarios.filter(horarioauladiario__isnull=False) | qs_diarios.filter(turno__descricao='EAD') | qs_diarios_com_pratica_profissional
            )
            qs_diarios = qs_diarios.distinct().order_by('turma__curso_campus')
            qs_diarios = qs_diarios.filter(turma__curso_campus=curso_escolhido)
            turmas = Turma.objects.filter(diario__in=qs_diarios).distinct()
        else:
            turmas = None
            curso_escolhido = None
        if request.GET.get('turma'):
            turma_escolhida = get_object_or_404(Turma, pk=request.GET.get('turma'))
        else:
            turma_escolhida = None

    if tab == 'monitoramento':
        diarios_quantitativos = obj.get_diarios_quantitativos(curso=curso_escolhido, turma=turma_escolhida)
        qtd_diarios_quantitativos = len(diarios_quantitativos)

    diarios_sem_horarios = obj.get_diarios_sem_horarios(curso=curso_escolhido, turma=turma_escolhida).select_related(
        'componente_curricular', 'componente_curricular__componente', 'turma__curso_campus'
    )

    deve_exibir_outras_configuracoes = Configuracao.get_valor_por_chave('edu', 'permite_requerer_quebra_requisito_aumento_ch') or any(
        (obj.permite_requerimento_quebra_de_requisito, obj.permite_requerimento_ultrapassar_ch_maxima)
    )

    return locals()


@permission_required('edu.efetuar_matricula')
@login_required()
@rtr()
def processar_pedidos_matricula(request, pk):
    obj = get_object_or_404(ConfiguracaoPedidoMatricula, pk=pk)
    if not request.user.is_superuser and not obj.pode_processar():
        return httprr('..', 'O pedido não pode ser processado.', 'error')
    return tasks.processar_pedidos_matricula(obj)


@rtr()
def meu_pedido_matricula(request, pk):
    title = 'Pedidos de renovação de matrícula'
    obj = get_object_or_404(PedidoMatricula, pk=pk)
    if not request.user.is_authenticated and 'matricula_aluno_como_resposavel' not in request.session:
        raise PermissionDenied

    if not (
        obj.matricula_periodo.aluno.get_user().username == request.session.get('matricula_aluno_como_resposavel')
        or obj.matricula_periodo.aluno.get_user() == request.user
        or request.user.has_perm('edu.efetuar_matricula')
        or request.user.has_group_cached('Visualizador de Informações Acadêmicas, Auditor,Estagiário Acadêmico Sistêmico')
    ):
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    pedidos_matricula_diario = obj.pedidomatriculadiario_set.all()
    diarios_removidos = []
    for pedido_matricula_diario in pedidos_matricula_diario.filter(deferido=True):
        if not MatriculaDiario.objects.filter(diario=pedido_matricula_diario.diario, matricula_periodo=obj.matricula_periodo).exists():
            diarios_removidos.append(pedido_matricula_diario.diario)
    turnos = obj.get_horarios()
    return locals()


@permission_required('edu.add_configuracaopedidomatricula')
@rtr()
def monitoramento_fechamento_periodo(request):
    title = 'Monitoramento de Fechamento de Período'

    periodo_letivo_atual = PeriodoLetivoAtual.get_instance(request)
    ano_letivo = Ano.objects.get(ano=periodo_letivo_atual.ano).pk
    periodo_letivo = periodo_letivo_atual.periodo
    diretorias = Diretoria.locals.all()
    initial = {'ano_letivo': ano_letivo, 'periodo_letivo': periodo_letivo, 'diretorias': diretorias}
    form = MonitoramentoFechamentoPeriodoForm(request.GET or None, request=request, initial=initial)

    if form.is_valid():
        matriculas_periodos, graficos = form.processar()
        agrupamento = form.cleaned_data['agrupamento']

    return locals()


@login_required()
@rtr()
def monitoramento_entrega_diarios(request):
    title = 'Monitoramento de Entrega de Diários'

    periodo_letivo_atual = PeriodoLetivoAtual.get_instance(request)
    ano_letivo = Ano.objects.get(ano=periodo_letivo_atual.ano).pk
    periodo_letivo = periodo_letivo_atual.periodo
    diretorias = Diretoria.locals.all()
    initial = {'ano_letivo': ano_letivo, 'periodo_letivo': periodo_letivo, 'diretorias': diretorias}
    form = MonitoramentoEntregaDiariosForm(request.GET or None, request=request, initial=initial)

    if form.is_valid():
        com_grafico = not request.user.has_group_cached('Administrador Acadêmico')
        professores_diario, graficos = form.processar(com_grafico)
        qtd_diarios = professores_diario.values_list('diario__id', flat=True).distinct().count()
        qtd_professores = professores_diario.values_list('professor__id', flat=True).distinct().count()
        agrupamento = form.cleaned_data['agrupamento']

    return locals()


@rtr()
@permission_required('edu.view_configuracaopedidomatricula')
def acompanhamento_matricula_turma(request):
    title = 'Matrícula de Ingressantes na Turma'
    form = MatriculaIngressosTurmaForm(request.GET or None)
    if form.is_valid():
        turmas, alunos_aptos_matricular = form.processar()
        qtd_turmas = len(turmas)
        alunos_sem_turma_geradas = (
            Aluno.get_ingressantes_sem_turma(
                form.cleaned_data['ano_letivo'], form.cleaned_data['periodo_letivo'], form.cleaned_data['diretoria'], form.cleaned_data['curso']
            )
            .exclude(id__in=alunos_aptos_matricular)
            .distinct()
            .order_by('pessoa_fisica__nome')
        )
        qtd_alunos_sem_turma_geradas = alunos_sem_turma_geradas.count()
        alunos_com_turma_geradas = Aluno.objects.filter(id__in=alunos_aptos_matricular).order_by('pessoa_fisica__nome')
        qtd_alunos_com_turma_geradas = alunos_com_turma_geradas.count()
        qtd_alunos = qtd_alunos_sem_turma_geradas + qtd_alunos_com_turma_geradas
    return locals()


@rtr()
@permission_required('edu.view_configuracaopedidomatricula')
def visualizar_alunos_pedido_diario(request, pk_configuracao, pk_diario):
    configuracao = get_object_or_404(ConfiguracaoPedidoMatricula, pk=pk_configuracao)
    diario = get_object_or_404(Diario, pk=pk_diario)
    title = str(diario)
    pedidos_alunos_diario = PedidoMatriculaDiario.objects.filter(
        diario__id=pk_diario, pedido_matricula__configuracao_pedido_matricula__pk=pk_configuracao
    ).order_by('pedido_matricula__matricula_periodo__aluno__pessoa_fisica__nome')
    return locals()


@rtr()
@login_required()
def videos(request):
    title = 'Vídeo-Aula - Efetuar Matrícula por Processo Seletivo'
    return locals()


@permission_required('edu.change_configuracaopedidomatricula')
@rtr()
def replicar_configuracao_pedido_matricula(request, pk):
    configuracao_pedido_matricula = get_object_or_404(ConfiguracaoPedidoMatricula, pk=pk)
    title = f'Replicação da Configuração de Pedido de Matrícula - {configuracao_pedido_matricula.descricao}'
    initial = {
        'descricao': f'{configuracao_pedido_matricula.descricao} [NOVA CHAMADA]',
        'impedir_troca_turma': configuracao_pedido_matricula.impedir_troca_turma,
        'restringir_por_curso': configuracao_pedido_matricula.restringir_por_curso,
        'requer_atualizacao_dados': configuracao_pedido_matricula.requer_atualizacao_dados,
        'requer_atualizacao_caracterizacao': configuracao_pedido_matricula.requer_atualizacao_caracterizacao,
        'permite_requerimento_quebra_de_requisito': configuracao_pedido_matricula.permite_requerimento_quebra_de_requisito,
        'permite_requerimento_ultrapassar_ch_maxima': configuracao_pedido_matricula.permite_requerimento_ultrapassar_ch_maxima,
        'data_limite_requerimentos_especiais': configuracao_pedido_matricula.data_limite_requerimentos_especiais,
    }
    form = ReplicacaoConfiguracaoPedidoMatriculaForm(data=request.POST or None, initial=initial)
    if request.POST and form.is_valid():
        try:
            resultado = form.processar(configuracao_pedido_matricula)
            return httprr(f'/edu/configuracao_pedido_matricula/{resultado.pk}/', 'Configuração de Renovação de Matrícula replicada com sucesso.')
        except ValidationError as e:
            return httprr('.', f'Não foi possível replicar a Configuração de Renovação de Matrícula: {e.messages[0]}', 'error')
    return locals()


@rtr()
@login_required()
def editar_matricula_diario_resumida(request, matricula_diario_resumida_pk):
    obj = get_object_or_404(MatriculaDiarioResumida, pk=matricula_diario_resumida_pk)
    aluno = obj.matricula_periodo.aluno
    title = 'Editar Registro de Histórico'
    form = EditarMatriculaDiarioResumidaForm(data=request.POST or None, instance=obj)

    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, aluno.curso_campus)

    if not pode_realizar_procedimentos:
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    if form.is_valid():
        form.save(request)
        aluno.atualizar_situacao('Reprocessamento do Histórico')
        return httprr('..', 'Matrícula Diário Resumida atualizada com sucesso.')

    return locals()


@rtr()
@login_required()
def componentes_nao_disponiveis_matricula_online(request, aluno_pk):
    aluno = get_object_or_404(Aluno.locals, pk=aluno_pk)

    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, aluno.curso_campus)
    if not pode_realizar_procedimentos and not aluno.is_user(request):
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    if not aluno.pode_matricula_online():
        return httprr('/', 'Não existe um período de renovação de matrícula ativa para o seu curso.', 'error')

    if aluno.is_credito():
        title = 'Disciplinas {} pendentes não disponíveis'.format(request.GET.get('optativas') == '1' and 'optativas' or 'obrigatórias')

    turma = None
    if aluno.is_seriado() or aluno.is_modular():
        if request.GET.get('turma'):
            turma = get_object_or_404(Turma, pk=request.GET.get('turma'))
            title = f'Disciplinas da turma({turma}) não disponíveis'
        else:
            title = 'Disciplinas em dependência não disponíveis'

    componentes_nao_disponiveis = aluno.componentes_nao_disponiveis_matricula_online(request.GET.get('optativas'), turma)
    return locals()


@rtr()
@permission_required('edu.efetuar_matricula')
def enviar_fotos_lote(request):
    title = 'Atualizar Fotos de Alunos em Lote'

    if request.POST:
        form = AtualizarFotosAlunosForm(request=request, data=request.POST, files=request.FILES)
    else:
        form = AtualizarFotosAlunosForm()

    if form.is_valid():
        arquivos_problema = form.processar()
        if not arquivos_problema:
            return httprr('.', 'Fotos atualizadas com sucesso.')
    return locals()


@rtr()
@permission_required('edu.view_configuracaopedidomatricula')
def alunos_conflitos_horarios(request):
    title = 'Relatório de Alunos com Conflitos de Horários'
    form = AlunosConflitosHorariosForm(request.GET or None)
    if form.is_valid():
        alunos_conflitos_horarios = form.processar()
    return locals()


@rtr()
@permission_required('edu.view_configuracaopedidomatricula')
def visualizar_alunos_configuracao_pedido_matricula(request, configuracao_pedido_matricula_pk, curso_pk):
    if 'situacao' in request.GET:
        configuracao_pedido_matricula = get_object_or_404(ConfiguracaoPedidoMatricula, pk=configuracao_pedido_matricula_pk)
        curso = get_object_or_404(CursoCampus, pk=curso_pk)

        situacao_alunos_configuracao = request.GET.get('situacao')
        if situacao_alunos_configuracao == 'aptos':
            title = 'Alunos Aptos'
            alunos = configuracao_pedido_matricula.get_alunos_aptos(curso)
        elif situacao_alunos_configuracao == 'participantes':
            title = 'Alunos Participantes'
            alunos = configuracao_pedido_matricula.get_alunos_participantes(curso)
        elif situacao_alunos_configuracao == 'nao_participantes':
            title = 'Alunos Não Participantes'
            alunos = configuracao_pedido_matricula.get_alunos_nao_participantes(curso)
    return locals()


@rtr()
@login_required()
def lancar_credito_especial(request, aluno_pk, pk_ce=None):
    obj = get_object_or_404(Aluno.locals, pk=aluno_pk)
    title = 'Lançamento de Crédito Especial'
    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, obj.curso_campus)
    if not pode_realizar_procedimentos:
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')
    instance = None
    if pk_ce:
        instance = CreditoEspecial.objects.get(pk=pk_ce)
        title = f'Editar Lançamento de Crédito Especial - {instance}'
    form = CreditoEspecialForm(obj, data=request.POST or None, instance=instance)
    if form.is_valid():
        form.save()
        return httprr('..', 'Crédito Especial lançado com sucesso.')
    return locals()


@login_required()
@rtr()
def visualizar_certificacao(request, aluno_pk, componente_curricular_pk):
    title = 'Visualizar Certificação do Conhecimento'
    obj = CertificacaoConhecimento.objects.filter(matricula_periodo__aluno_id=aluno_pk, componente_curricular_id=componente_curricular_pk).first()
    if obj is None:
        return httprr('..', 'Este registro de certificação de conhecimento não foi encontrado.', 'error', close_popup=True)
    is_lancamento_conceito = obj.matricula_periodo.aluno.matriz.estrutura.is_lancamento_conceito()
    return locals()


@login_required()
@rtr()
def visualizar_aproveitamento(request, aluno_pk, componente_curricular_pk):
    title = 'Visualizar Aproveitamento'
    obj = AproveitamentoEstudo.objects.filter(matricula_periodo__aluno_id=aluno_pk, componente_curricular_id=componente_curricular_pk).first()
    if obj is None:
        return httprr('..', 'Este registro de aproveitamento não foi encontrado.', 'error', close_popup=True)
    is_lancamento_conceito = obj.matricula_periodo.aluno.matriz.estrutura.is_lancamento_conceito()
    return locals()


@login_required()
@rtr()
def visualizar_equivalencia(request, aluno_pk, componente_curricular_pk):
    title = 'Visualizar Equivalência'
    obj = AproveitamentoComponente.objects.filter(matricula_periodo__aluno__pk=aluno_pk, componente_curricular__pk=componente_curricular_pk).first()
    return locals()


@rtr()
@permission_required('edu.change_requerimento')
def indeferir_requerimento(request, pk):
    title = 'Indeferir Requerimento'
    obj = get_object_or_404(Requerimento, pk=pk).sub_instance()
    form = IndeferirRequerimentoForm(data=request.POST or None, instance=obj)
    if form.is_valid():
        obj.indeferir(request.user)
        return httprr('..', 'Requerimento indeferido com sucesso.')
    return locals()


@rtr()
@permission_required('edu.view_requerimento')
def requerimento(request, pk):
    title = 'Requerimento'
    obj = Requerimento.get_queryset(request.user).filter(pk=pk).first()
    if obj is None:
        return httprr('..', 'Você não possui permissão para isso.', 'error')
    obj = obj.sub_instance() or obj
    if request.user.eh_aluno and obj.aluno.matricula != request.user.username:
        return httprr('..', 'Você não possui permissão para isso.', 'error')
    if isinstance(obj, RequerimentoAproveitamentoEstudo):
        if obj.solicitacaoaproveitamentoestudo_set.exists():
            return HttpResponseRedirect(f'/edu/requerimento_aproveitamento_estudo/{obj.pk}/')
    pode_visualizar = request.user.has_perm('edu.view_requerimento')
    if not pode_visualizar:
        return httprr('..', 'Você não possui permissão para visualizar esse registro.', 'error')
    is_coordenador = request.user.get_vinculo().id in (obj.aluno.curso_campus.coordenador_id, obj.aluno.curso_campus.coordenador_2_id)
    pode_realizar_procedimentos = request.user.has_perm('edu.change_requerimento')
    if pode_realizar_procedimentos and 'processar' in request.GET and obj.pode_ser_executado_automaticamente():
        try:
            obj.processar(request.user)
            return httprr('.', 'Requerimento atendido com sucesso.')
        except ValidationError as e:
            return httprr('.', e.message, 'error')

    elif pode_realizar_procedimentos:
        form = AvaliacaoRequerimentoForm(data=request.POST or None, instance=obj)
        if form.is_valid():
            form.save(user=request.user)
            return httprr('.', 'Avaliação realizada com sucesso.')

    alertas = []
    nada_consta_quite = True
    if obj.tipo == Requerimento.MATRICULA_DISCIPLINA:
        if obj.diario is None:
            alertas.append('Este requerimento não possui um diário.')
        else:
            eh_da_matriz = obj.aluno.matriz.componentecurricular_set.filter(componente=obj.diario.componente_curricular.componente).exists()
            if not eh_da_matriz:
                alertas.append('Este componente não pertence à matriz do aluno.')
                _, msg_validacao = obj.aluno.pode_cursar_componente_curricular(obj.diario.componente_curricular, outra_matriz=True)
                if msg_validacao:
                    alertas.append(msg_validacao)
    if obj.tipo == Requerimento.TRANCAMENTO_MATRICULA:
        if obj.aluno.possui_pendencia_nada_consta(ProcedimentoMatricula.TRANCAMENTO_VOLUNTARIO):
            alertas.append('Este requerimento exige a quitação de itens de nada consta.')
            nada_consta_quite = False
    return locals()


@login_required()
@rtr()
def requerimento_aproveitamento_estudo(request, pk):
    vinculo = request.user.get_vinculo()
    title = 'Requerimento de Aproveitamento de Estudo'
    obj = get_object_or_404(RequerimentoAproveitamentoEstudo.objects, pk=pk)
    is_proprio_aluno = obj.aluno.is_user(request)
    is_coordenador = obj.aluno.curso_campus.coordenador_id == vinculo.id or obj.aluno.curso_campus.coordenador_2_id == vinculo.id
    pode_finalizar = is_proprio_aluno and obj.pode_finalizar_cadastro()[0]
    possui_solicitacoes = obj.solicitacaoaproveitamentoestudo_set.exists()
    pode_desarquivar = obj.atendente == request.user and obj.is_arquivado()

    if obj.is_arquivado():
        if 'desarquivar' in request.GET and pode_desarquivar:
            obj.desarquivar()
            return httprr(request.path, 'Situação alterada com sucesso.')
    else:
        if 'finalizar' in request.GET and pode_finalizar:
            obj.situacao = 'Em Andamento'
            obj.save()
            obj.solicitacaoaproveitamentoestudo_set.update(situacao=SolicitacaoAproveitamentoEstudo.SITUACAO_SOLICITADA)
            return httprr(request.path, 'Solicitação finalizada e enviada com sucesso.', close_popup=True)

        if 'cancelar_avaliacao' in request.GET and is_coordenador and obj.aluno.is_matriculado():
            registro = obj.solicitacaoaproveitamentoestudo_set.get(pk=request.GET['cancelar_avaliacao'])
            if registro.is_finalizada():
                registro.cancelar_avaliacao()
            return httprr(request.path, 'Cancelamento de avaliação realizado com sucesso.', close_popup=True)
    return locals()


@login_required()
@rtr()
def adicionar_solicitacao_aproveitamento_disciplina(request, pk, pk2=None):
    title = 'Adicionar Disciplina'
    vinculo = request.user.get_vinculo()
    try:
        obj = RequerimentoAproveitamentoEstudo.objects.get(pk=pk)
    except RequerimentoAproveitamentoEstudo.DoesNotExist:
        return httprr('..', 'Este requerimento não existe ou foi excluído do sistema.', 'error', close_popup=True)
    is_coordenador = obj.aluno.curso_campus.coordenador_id == vinculo.id or obj.aluno.curso_campus.coordenador_2_id == vinculo.id
    instance = SolicitacaoAproveitamentoEstudo.objects.get(pk=pk2).subinstance() if pk2 else None
    if instance and (instance.requerimento.aluno.get_vinculo() != vinculo and not is_coordenador):
        return httprr('..', 'Você não tem permissão para isso.', 'error', close_popup=True)
    cls = SolicitacaoAproveitamentoEstudoInternoFom if obj.interno else SolicitacaoAproveitamentoEstudoExternoFom
    form = cls(data=request.POST or None, files=request.FILES or None, requerimento=obj, request=request, instance=instance)
    if form.is_valid():
        form.instance.requerimento = obj
        form.save()
        return httprr('..', 'Solicitação adicionada com sucesso.', close_popup=True)
    return locals()


@rtr()
@permission_required('edu.change_requerimento')
def encaminhar_solicitacao_aproveitamento_disciplina(request, pk):
    title = 'Informar Avaliador'
    vinculo = request.user.get_vinculo()
    obj = get_object_or_404(SolicitacaoAproveitamentoEstudo.objects, pk=pk).subinstance()
    is_coordenador = (
        obj.requerimento.aluno.curso_campus.coordenador_id == vinculo.id or obj.requerimento.aluno.curso_campus.coordenador_2_id == vinculo.id
    )
    if not is_coordenador:
        return HttpResponseForbidden()
    form = EncaminharSolicitacaoAproveitamentoEstudoForm(data=request.POST or None, request=request)
    form.fields['avaliador'].initial = obj.avaliador_id or None
    form.fields['avaliador'].queryset = form.fields['avaliador'].queryset.filter(vinculo__ativo=True)
    if form.is_valid():
        obj.avaliador = form.cleaned_data['avaliador']
        if obj.avaliador:
            obj.situacao = SolicitacaoAproveitamentoEstudo.SITUACAO_EM_ANALISE
            obj.avaliador.vinculo.user.groups.add(obj.avaliador.vinculo.user.groups.model.objects.get_or_create(name='Avaliador de Requerimento')[0])
        else:
            obj.situacao = SolicitacaoAproveitamentoEstudo.SITUACAO_SOLICITADA
        obj.parecer = None
        obj.save()
        if obj.requerimento.atendente_id is None:
            obj.requerimento.inicio = datetime.date.today()
            obj.requerimento.atendente = request.user
            obj.requerimento.save()
        return httprr('..', 'Ação realizada com sucesso.')
    return locals()


@rtr()
@permission_required('edu.change_requerimento')
def avaliar_solicitacao_aproveitamento_disciplina(request, pk):
    title = 'Avaliar Solicitação'
    obj = get_object_or_404(SolicitacaoAproveitamentoEstudo.objects, pk=pk).subinstance()
    if obj.avaliador is None or obj.avaliador.vinculo != request.user.get_vinculo():
        return httprr('..', 'Você não tem permissão para avaliar esta solicitação.', 'error')
    if obj.situacao == SolicitacaoAproveitamentoEstudo.SITUACAO_INDEFERIDA:
        return httprr('..', 'Esta solicitação foi cancelada/indeferida e não pode ser avaliada.', 'error')
    form = AvaliarSolicitacaoAproveitamentoEstudoForm(data=request.POST or None, request=request, solicitacao=obj)
    form.fields['parecer'].initial = obj.parecer_id or None
    if form.is_valid():
        obj.parecer = form.cleaned_data['parecer']
        obj.observacao = form.cleaned_data['observacao']
        if obj.parecer:
            if obj.parecer.apto:
                obj.situacao = (
                    SolicitacaoAproveitamentoEstudo.SITUACAO_DEFERIDA if obj.parecer.deferido else SolicitacaoAproveitamentoEstudo.SITUACAO_INDEFERIDA
                )
            else:
                obj.situacao = SolicitacaoAproveitamentoEstudo.SITUACAO_EM_ANALISE
            if obj.parecer.deferido:
                obj.gerar_aproveitamento()
            else:
                obj.excluir_aproveitamento()
        else:
            obj.situacao = SolicitacaoAproveitamentoEstudo.SITUACAO_EM_ANALISE
            obj.excluir_aproveitamento()
        obj.save()
        obj.requerimento.atualizar_situacao()
        return httprr('..', 'Ação realizada com sucesso.')
    return locals()


@rtr()
@permission_required('edu.change_requerimento')
def desarquivar_requerimento(request, pk):
    obj = Requerimento.objects.get(pk=pk)
    if obj and obj.situacao == 'Arquivado':
        obj.situacao = 'Em Andamento'
        obj.deferido = None
        obj.save()
        return httprr(f'/edu/requerimento/{pk}/', 'Requerimento desarquivado com sucesso.')
    else:
        return httprr(f'/edu/requerimento/{pk}/', 'Não foi possível desarquivar o requerimento.', 'error')


@login_required()
@rtr()
def adicionar_premiacao(request, aluno_pk, premiacao_pk=None):
    title = ' {} Premiação'.format(premiacao_pk and 'Editar' or 'Adicionar')

    premiacao = None
    if premiacao_pk:
        premiacao = Premiacao.objects.get(pk=premiacao_pk)

    aluno = get_object_or_404(Aluno, pk=aluno_pk)
    is_diretor_geral = (
        request.user.has_group_cached('Diretor Geral') and aluno.curso_campus.diretoria.diretor_geral_id == request.user.get_vinculo().id
    )
    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, aluno.curso_campus)
    if not pode_realizar_procedimentos and not is_diretor_geral:
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    form = PremiacaoForm(aluno, request.POST or None, instance=premiacao)

    if form.is_valid():
        obj = form.save()

        if not premiacao_pk:
            return httprr('..', 'Premiação adicionada com sucesso.')
        else:
            return httprr('..', 'Premiação atualizada com sucesso.')

    return locals()


@login_required()
@rtr()
def adicionar_medida_disciplinar(request, aluno_pk, medida_pk=None):
    title = ' {} Medida Disciplinar'.format(medida_pk and 'Editar' or 'Adicionar')

    medida = None
    if medida_pk:
        medida = MedidaDisciplinar.objects.get(pk=medida_pk)

    aluno = get_object_or_404(Aluno, pk=aluno_pk)
    is_diretor_geral = (
        request.user.has_group_cached('Diretor Geral') and aluno.curso_campus.diretoria.diretor_geral_id == request.user.get_vinculo().id
    )
    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, aluno.curso_campus)
    if not pode_realizar_procedimentos and not is_diretor_geral:
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    form = MedidaDisciplinarForm(aluno, request.POST or None, instance=medida)

    if form.is_valid():
        obj = form.save()

        if not medida_pk:
            return httprr('..', 'Medida Disciplinar adicionada com sucesso.')
        else:
            return httprr('..', 'Medida Disciplinar atualizada com sucesso.')

    return locals()


@permission_required('edu.importar_aluno')
@rtr()
def importar_aluno_qacademico(request, pk):
    aluno = Aluno.objects.get(pk=pk)
    dao = DAO()
    dao.importar_alunos(prefixo_matricula=aluno.matricula, verbose=False)
    dao.importar_matriculas_periodo(prefixo_matricula=aluno.matricula, verbose=False)
    dao.importar_registros_diploma(matricula=aluno.matricula)
    return httprr(f'/edu/aluno/{aluno.matricula}/', 'Aluno importado com sucesso.')


@rtr()
@permission_required('comum.is_migrador_edu')
def importar_componente_csv(request):
    title = 'Migração de dados - Componentes'
    form = ImportarComponenteCSVForm(data=request.POST or None, files=request.FILES or None, request=request)
    if form.is_valid():
        return form.processar()
    return locals()


@rtr()
@permission_required('comum.is_migrador_edu')
def importar_curso_csv(request):
    title = 'Migração de dados - Cursos'
    form = ImportarCursoCSVForm(data=request.POST or None, files=request.FILES or None, request=request)
    if form.is_valid():
        return form.processar()
    return locals()


@rtr()
@permission_required('comum.is_migrador_edu')
def importar_matriz_csv(request):
    title = 'Migração de dados - Matrizes'
    form = ImportarMatrizCSVForm(data=request.POST or None, files=request.FILES or None, request=request)
    if form.is_valid():
        return form.processar()
    return locals()


@rtr()
@permission_required('comum.is_migrador_edu')
def importar_aluno_csv_v2(request):
    title = 'Migração de dados - Alunos'
    form = ImportarAlunoCSVFormV2(data=request.POST or None, files=request.FILES or None, request=request)
    if form.is_valid():
        return form.processar()
    return locals()


@rtr()
@permission_required('comum.is_migrador_edu')
def importar_historico_aluno_csv(request):
    title = 'Migração de dados - Históricos'
    form = ImportarHistoricoAlunoCSVForm(data=request.POST or None, files=request.FILES or None, request=request)
    if form.is_valid():
        return form.processar()
    return locals()


@rtr()
@permission_required('comum.is_migrador_edu')
def importar_procedimento_matricula_csv(request):
    title = 'Migração de dados - Procedimentos de matrícula'
    form = ImportarProcedimentoMatriculaCSVForm(data=request.POST or None, files=request.FILES or None, request=request)
    if form.is_valid():
        return form.processar()
    return locals()


@rtr()
@permission_required('comum.is_migrador_edu')
def importar_equivalencia_csv(request):
    title = 'Migração de dados - Equivalências'
    form = ImportarEquivalenciaCSVForm(data=request.POST or None, files=request.FILES or None, request=request)
    if form.is_valid():
        return form.processar()
    return locals()


@rtr()
@permission_required('comum.is_migrador_edu')
def inicializar_periodo_letivo(request):
    title = 'Migração de dados - Inicializar período letivo'
    form = InicializarPeriodoLetivoForm(data=request.POST or None, files=request.FILES or None, request=request)
    if form.is_valid():
        return form.processar()
    return locals()


@permission_required('edu.efetuar_matricula')
@rtr()
def integralizar_alunos(request, matriz_id):
    erros = request.session.get('pendencias_integralizacao')
    if 'xls' in request.GET and erros:
        rows = [['#', 'Aluno', 'Matrícula', 'Pendência']]
        count = 0
        for erro in erros:
            for mensagem in erro['mensagens']:
                count += 1
                row = [count, erro['aluno'], erro['matricula'], mensagem]
                rows.append(row)
        return XlsResponse(rows)

    title = 'Migração de Alunos Ativos do Q-Acadêmico'
    ano_corrente = get_object_or_404(Ano, ano=datetime.datetime.now().year)
    initial = {'ano_letivo': ano_corrente.id}
    form = ImportarAlunosAtivosForm(matriz_id, data=request.POST or None, files=request.POST and request.FILES or None, initial=initial)
    if form.is_valid():
        return form.processar(request)
    else:
        try:
            request.session['pendencias_integralizacao'] = [
                {'aluno': aluno.get_nome_social_composto(), 'matricula': aluno.matricula, 'mensagens': mensagens} for aluno, mensagens in form.erros
            ]
        except Exception:
            pass

    return locals()


@group_required('Administrador Acadêmico, edu Administrador, Secretário Acadêmico')
@rtr()
@login_required()
def desfazer_migracao(request, pk):
    obj = get_object_or_404(Aluno, pk=pk)
    title = f'Desfazer Migração de {obj.get_nome_social_composto()} ({obj.matricula})'
    enade = RegistroConvocacaoENADE.objects.filter(aluno=obj).count()
    projeto_final = ProjetoFinal.objects.filter(matricula_periodo__aluno=obj).count()
    matriculas_diarios = MatriculaDiario.objects.filter(matricula_periodo__aluno=obj).count()
    pedidos_matricula = PedidoMatricula.objects.filter(matricula_periodo__aluno=obj).count()
    procedimentos_matricula = ProcedimentoMatricula.objects.filter(matricula_periodo__aluno=obj).count()
    pode_desfazer_migracao_total = request.user.has_group_cached('Administrador Acadêmico')
    if 'confirmar' in request.GET:
        if 'parcial' in request.GET:
            obj.desfazer_migracao_qacademico()
        else:
            if not pode_desfazer_migracao_total:
                return httprr('..', 'Você não possui permissão para isso.', 'error')
            obj.desfazer_migracao()
        return httprr('..', 'Procedimento realizado com sucesso.')

    return locals()


@group_required('Migrador edu, Secretário Acadêmico')
@rtr()
def inconsistencias(request):
    if not request.user.has_group_cached('Administrador Acadêmico') and not Configuracao.get_valor_por_chave(
        'edu', 'relatorio_inconsistencia_descentralizado'
    ):
        return httprr('/', 'Você não possui permissão para isso.', 'error')
    title = 'Listagem de inconsistências'
    inconsistencias = []
    form = InconsistenciasForm(data=request.POST or None)
    if form.is_valid():
        inconsistencias = form.processar()
        tipo = form.cleaned_data['tipo']
    return locals()


@group_required('Migrador edu, Secretário Acadêmico')
@rtr()
def corrigir_inconsistencia_situacao(request, matricula_periodo_id, situacao_id):
    if not request.user.has_group_cached('Administrador Acadêmico') and not Configuracao.get_valor_por_chave(
        'edu', 'relatorio_inconsistencia_descentralizado'
    ):
        return httprr('/', 'Você não possui permissão para isso.', 'error')
    mp = MatriculaPeriodo.objects.get(id=matricula_periodo_id)
    mp.situacao_id = situacao_id
    mp.save()
    dict_resposta = {
        'msg': 'Correção aplicada com sucesso.',
    }
    return JsonResponse(dict_resposta)


@group_required('Migrador edu, Secretário Acadêmico')
@rtr()
def corrigir_inconsistencia_periodo(request, matricula):
    if not request.user.has_group_cached('Administrador Acadêmico') and not Configuracao.get_valor_por_chave(
        'edu', 'relatorio_inconsistencia_descentralizado'
    ):
        return httprr('/', 'Você não possui permissão para isso.', 'error')
    aluno = Aluno.objects.get(matricula=matricula)
    aluno.atualizar_periodo_referencia()
    dict_resposta = {
        'msg': 'Correção aplicada com sucesso.',
    }
    return JsonResponse(dict_resposta)


@group_required('Migrador edu, Secretário Acadêmico')
@rtr()
def corrigir_inconsistencia_periodo_referencia_periodo_letivo(request, pk):
    if not request.user.has_group_cached('Administrador Acadêmico') and not Configuracao.get_valor_por_chave(
        'edu', 'relatorio_inconsistencia_descentralizado'
    ):
        return httprr('/', 'Você não possui permissão para isso.', 'error')
    mp = MatriculaPeriodo.objects.get(pk=pk)
    mp.aluno.verificar_periodo_referencia_em_periodos_letivos(corrigir_periodo=int(pk))
    dict_resposta = {
        'msg': 'Correção aplicada com sucesso.',
    }
    return JsonResponse(dict_resposta)


@group_required('Migrador edu, Secretário Acadêmico')
@rtr()
def corrigir_inconsistencia_matricula_periodo(request, matricula):
    if not request.user.has_group_cached('Administrador Acadêmico') and not Configuracao.get_valor_por_chave(
        'edu', 'relatorio_inconsistencia_descentralizado'
    ):
        return httprr('/', 'Você não possui permissão para isso.', 'error')
    aluno = Aluno.objects.get(matricula=matricula)
    mp = aluno.get_ultima_matricula_periodo()
    ano_letivo = Ano.objects.get_or_create(ano=datetime.date.today().year)[0]
    periodo_matriz = 1
    if mp:
        if aluno.is_credito():
            periodo_matriz = mp.periodo_matriz + 1
        else:
            if mp.situacao_id in (SituacaoMatriculaPeriodo.APROVADO, SituacaoMatriculaPeriodo.DEPENDENCIA):
                periodo_matriz = mp.periodo_matriz + 1
            else:
                periodo_matriz = mp.periodo_matriz
    MatriculaPeriodo.objects.create(
        ano_letivo=ano_letivo, periodo_letivo=1, aluno=aluno, situacao_id=SituacaoMatriculaPeriodo.EM_ABERTO, periodo_matriz=periodo_matriz
    )
    dict_resposta = {
        'msg': 'Correção aplicada com sucesso.',
    }
    return JsonResponse(dict_resposta)


@group_required('Administrador Acadêmico, Secretário Acadêmico')
@rtr()
def cadastrar_procedimento_matricula(request, pk):
    if not Configuracao.get_valor_por_chave('edu', 'pode_cadastrar_procedimento_matricula'):
        return httprr('..', 'Você não possui permissão para isso.', 'error')
    aluno = Aluno.objects.get(pk=pk)
    title = 'Cadastrar Procedimento de Matrícula'
    form = ProcedimentoMatriculaManualForm(data=request.POST or None)
    form.fields['matricula_periodo'].queryset = aluno.matriculaperiodo_set.filter(procedimentomatricula__isnull=True)
    if form.is_valid():
        form.instance.identificador_externo = 999999999
        form.save()
        return httprr('..', 'Procedimento realizado com sucesso.')
    return locals()


@login_required()
@rtr()
def cadastrar_justificativa_falta(request):
    title = 'Cadastrar Justificativa de Falta'
    if not request.user.eh_aluno:
        return httprr('..', 'Você não possui permissão para isso.', 'error')
    aluno = Aluno.objects.get(matricula=request.user.username)
    form = CadastrarJustificativaFaltaForm(data=request.POST or None, request=request, files=request.FILES or None)
    if form.is_valid():
        form.instance.data_solicitacao = datetime.datetime.now()
        form.instance.responsavel_abono = None
        form.instance.deferido = None
        form.instance.aluno = aluno
        form.save()
        return httprr(f'/edu/abonofaltas/{form.instance.pk}/', 'Justificativa de falta cadastrada com sucesso.')
    return locals()


@login_required()
@rtr()
def solicitar_reposicao_atividade(request, pk):
    title = 'Solicitar reposição de atividade'
    obj = get_object_or_404(AbonoFaltas, pk=pk, aluno__matricula=request.user.username)
    if obj.deferido is not None:
        return HttpResponseForbidden()
    if 'remover' in request.GET:
        obj.solicitacaoreposicaoatividade_set.filter(pk=request.GET['remover']).delete()
        return httprr(f'/edu/abonofaltas/{obj.pk}/', 'Solicitação removida com sucesso.')
    else:
        form = SolicitarReposicaoAtividadeForm(data=request.POST or None, abono=obj)
        if form.is_valid():
            form.processar()
            return httprr(f'/edu/abonofaltas/{obj.pk}/', 'Solicitação adicionada com sucesso.', close_popup=True)
    return locals()


@login_required()
@rtr()
def avaliar_solicitacao_reposicao_atividade(request: HttpRequest, pk: int) -> dict[str, Any] | HttpResponse:
    title = 'Avaliar Solicitação'
    instance = get_object_or_404(SolicitacaoReposicaoAtividade, pk=pk)
    if not instance.abono_faltas.deferido:
        return HttpResponseForbidden()
    pks = instance.item_configuracao_avaliacao.configuracao_avaliacao.diario.professordiario_set.values_list('professor__vinculo__user', flat=True)
    pode_avaliar = request.user.id in pks
    if not pode_avaliar:
        return HttpResponseForbidden()
    form = AvaliarSolicitacaoReposicaoAtividadeForm(data=request.POST or None, request=request, instance=instance)
    if instance.deferida:
        del form.fields['deferida']
    else:
        form.fields['deferida'].required = True
        form.fields['deferida'].widget.choices = (
            ('', '-----'),
            (True, 'Sim'),
            (False, 'Não'),
        )
    if form.is_valid():
        form.instance.avaliador = request.user
        form.save()
        msg = f'A solicitação de reposição de atividade {instance.item_configuracao_avaliacao.sigla} do diário {instance.item_configuracao_avaliacao.configuracao_avaliacao.diario} foi avaliada. Acesse o SUAP para obter mais detalhes.'
        send_notification(
            'Avaliação de Justificativa de Falta', msg, settings.DEFAULT_FROM_EMAIL, [instance.abono_faltas.aluno.get_vinculo()], fail_silently=True
        )
        return httprr('..', 'Ação realizada com sucesso.')
    return locals()
