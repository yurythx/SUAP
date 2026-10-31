from __future__ import annotations

import datetime
import re
from unittest.mock import MagicMock, Mock, patch

import pytest
from django.core.exceptions import ValidationError
from django.db import transaction

from edu.models.alunos import Aluno
from edu.models.cadastros_gerais import SituacaoMatricula, SituacaoMatriculaPeriodo
from edu.models.historico import MatriculaDiario, MatriculaPeriodo
from comum.tests.factories import UserFactory
from edu.models.diarios import ConfiguracaoAvaliacao, ItemConfiguracaoAvaliacao
from edu.models.procedimentos import (
    AbonoFaltas,
    MotivoAusenciaEscolar,
    ParecerAvaliacaoAproveitamentoEstudo,
    ProcedimentoMatricula,
    Requerimento,
    SolicitacaoAproveitamentoEstudo,
    SolicitacaoReposicaoAtividade,
)
from edu.tests.factories import (
    AlunoFactory,
    DiarioFactory,
    MatriculaPeriodoFactory,
    ProcedimentoMatriculaFactory,
    ProfessorFactory,
    RequerimentoAproveitamentoEstudoFactory,
    RequerimentoFactory,
    SituacaoMatriculaFactory,
    SituacaoMatriculaPeriodoFactory,
    SolicitacaoAproveitamentoEstudoFactory,
)
from rh.tests.factories import ServidorFactory


@pytest.fixture
def motivo_com_previsao_normativa():
    return MotivoAusenciaEscolar(
        id=1,
        descricao='Motivo com previsao',
        possui_previsao_normativa=True,
        reposicao_obrigatoria=False,
        ativo=True,
    )


@pytest.fixture
def motivo_sem_previsao_normativa():
    return MotivoAusenciaEscolar(
        id=2,
        descricao='Motivo sem previsao',
        possui_previsao_normativa=False,
        reposicao_obrigatoria=False,
        ativo=True,
    )


def test_abono_deferido_sem_motivo_abona_faltas():
    abono = AbonoFaltas(deferido=True, motivo_ausencia_escolar=None)

    assert abono.deve_abonar_faltas() is True


def test_abono_deferido_com_motivo_previsto_em_norma_abona_faltas(motivo_com_previsao_normativa):
    abono = AbonoFaltas(deferido=True, motivo_ausencia_escolar=motivo_com_previsao_normativa)

    assert abono.deve_abonar_faltas() is True


def test_abono_deferido_sem_previsao_normativa_nao_abona_faltas(motivo_sem_previsao_normativa):
    abono = AbonoFaltas(deferido=True, motivo_ausencia_escolar=motivo_sem_previsao_normativa)

    assert abono.deve_abonar_faltas() is False


@pytest.mark.parametrize('deferido', [False, None])
def test_abono_nao_deferido_nunca_abona_faltas(deferido):
    abono = AbonoFaltas(deferido=deferido, motivo_ausencia_escolar=None)

    assert abono.deve_abonar_faltas() is False


@pytest.mark.parametrize(
    ('deferido', 'motivo', 'status_esperado'),
    [
        (None, None, 'Aguardando avaliação'),
        (False, None, 'Indeferida'),
        (True, None, 'Deferida'),
    ],
)
def test_abono_get_status_sem_motivo(deferido, motivo, status_esperado):
    abono = AbonoFaltas(deferido=deferido, motivo_ausencia_escolar=motivo)
    assert abono.get_status() == status_esperado


def test_abono_get_status_com_previsao_normativa(motivo_com_previsao_normativa):
    abono = AbonoFaltas(deferido=True, motivo_ausencia_escolar=motivo_com_previsao_normativa)
    assert abono.get_status() == 'Deferida'


def test_abono_get_status_sem_previsao_normativa_retorna_deferida(motivo_sem_previsao_normativa):
    abono = AbonoFaltas(deferido=True, motivo_ausencia_escolar=motivo_sem_previsao_normativa)
    assert abono.get_status() == 'Deferida'


def test_abono_a_criterio_do_docente_verdadeiro_apenas_quando_deferido_sem_previsao(motivo_com_previsao_normativa, motivo_sem_previsao_normativa):
    abono_sem_previsao = AbonoFaltas(deferido=True, motivo_ausencia_escolar=motivo_sem_previsao_normativa)
    assert abono_sem_previsao.abono_a_criterio_do_docente() is True

    abono_com_previsao = AbonoFaltas(deferido=True, motivo_ausencia_escolar=motivo_com_previsao_normativa)
    assert abono_com_previsao.abono_a_criterio_do_docente() is False

    abono_indeferido = AbonoFaltas(deferido=False, motivo_ausencia_escolar=motivo_sem_previsao_normativa)
    assert abono_indeferido.abono_a_criterio_do_docente() is False

    abono_pendente = AbonoFaltas(deferido=None, motivo_ausencia_escolar=motivo_sem_previsao_normativa)
    assert abono_pendente.abono_a_criterio_do_docente() is False

    abono_sem_motivo = AbonoFaltas(deferido=True, motivo_ausencia_escolar=None)
    assert abono_sem_motivo.abono_a_criterio_do_docente() is False


@pytest.mark.django_db
def test_abono_cancelar_deferimento_desfaz_deferimento_solicitacoes_reposicao():
    hoje = datetime.date.today()
    user = UserFactory()
    aluno = AlunoFactory()
    diario = DiarioFactory()
    configuracao = ConfiguracaoAvaliacao.objects.create(diario=diario, etapa=1)
    item = ItemConfiguracaoAvaliacao.objects.create(configuracao_avaliacao=configuracao, sigla='A1')
    abono = AbonoFaltas.objects.create(
        aluno=aluno,
        data_inicio=hoje,
        data_fim=hoje,
        deferido=True,
        responsavel_abono=user,
        observacao_avaliacao='Aprovado',
        data_avaliacao=hoje,
    )
    solicitacao = SolicitacaoReposicaoAtividade.objects.create(
        abono_faltas=abono,
        item_configuracao_avaliacao=item,
        deferida=True,
        data_reposicao=hoje,
        avaliador=user,
        observacao='Agendado para hoje',
    )

    abono.cancelar_deferimento()
    abono.refresh_from_db()
    solicitacao.refresh_from_db()

    assert abono.deferido is None
    assert abono.responsavel_abono is None
    assert abono.observacao_avaliacao is None
    assert abono.data_avaliacao is None

    assert solicitacao.deferida is None
    assert solicitacao.data_reposicao is None
    assert solicitacao.avaliador is None
    assert solicitacao.observacao is None


@pytest.mark.django_db
def test_abono_checar_solicitacoes_quando_indeferido_desfaz_deferimento_solicitacoes():
    hoje = datetime.date.today()
    user = UserFactory()
    aluno = AlunoFactory()
    diario = DiarioFactory()
    configuracao = ConfiguracaoAvaliacao.objects.create(diario=diario, etapa=1)
    item = ItemConfiguracaoAvaliacao.objects.create(configuracao_avaliacao=configuracao, sigla='A1')
    abono = AbonoFaltas.objects.create(
        aluno=aluno,
        data_inicio=hoje,
        data_fim=hoje,
        deferido=False,
    )
    solicitacao = SolicitacaoReposicaoAtividade.objects.create(
        abono_faltas=abono,
        item_configuracao_avaliacao=item,
        deferida=True,
        data_reposicao=hoje,
        avaliador=user,
        observacao='Agendado',
    )

    abono.checar_solicitacoes_reposicao_atividade()
    solicitacao.refresh_from_db()

    assert solicitacao.deferida is None
    assert solicitacao.data_reposicao is None
    assert solicitacao.avaliador is None
    assert solicitacao.observacao is None


@patch('edu.models.MatriculaPeriodo.objects.filter')
@patch('edu.models.procedimentos.AbonoFaltas.objects.filter')
def test_clean_valida_data_inicio_maior_data_fim(mock_abono_filter, mock_mp_filter):
    abono = AbonoFaltas(aluno_id=1, data_inicio=datetime.date(2023, 1, 10), data_fim=datetime.date(2023, 1, 5))
    with pytest.raises(ValidationError, match=re.escape('A data inicial não pode ser maior que a data final.')):
        abono.clean()


@patch('edu.models.MatriculaPeriodo.objects.filter')
@patch('edu.models.procedimentos.AbonoFaltas.objects.filter')
def test_clean_valida_sobreposicao_abonos(mock_abono_filter, mock_mp_filter):
    mock_abono_filter.return_value.exclude.return_value.exclude.return_value.exists.return_value = True

    abono = AbonoFaltas(aluno_id=1, data_inicio=datetime.date(2023, 1, 5), data_fim=datetime.date(2023, 1, 10), deferido=True)
    with pytest.raises(
        ValidationError, match=re.escape('Já existe uma justificativa deferida ou aguardando avaliação envolvendo o período informado.')
    ):
        abono.clean()


@patch('edu.models.MatriculaPeriodo.objects.filter')
@patch('edu.models.procedimentos.AbonoFaltas.objects.filter')
def test_clean_valida_matricula_periodos_fechados(mock_abono_filter, mock_mp_filter):
    mock_abono_filter.return_value.exclude.return_value.exclude.return_value.exists.return_value = False

    mock_mp_qs = mock_mp_filter.return_value.exclude.return_value.distinct.return_value
    mock_mp_qs.exists.return_value = True

    class MockMP:
        ano_letivo = 2023
        periodo_letivo = 1

    mock_mp_qs.__iter__.return_value = [MockMP()]

    abono = AbonoFaltas(aluno_id=1, data_inicio=datetime.date(2023, 1, 5), data_fim=datetime.date(2023, 1, 10), deferido=True)
    with pytest.raises(ValidationError, match=re.escape('No intervalo informado existem períodos já fechados: 2023 / 1.')):
        abono.clean()


@patch('edu.models.MatriculaPeriodo.objects.filter')
@patch('edu.models.procedimentos.AbonoFaltas.objects.filter')
def test_clean_passa_sem_erros(mock_abono_filter, mock_mp_filter):
    mock_abono_filter.return_value.exclude.return_value.exclude.return_value.exists.return_value = False
    mock_mp_filter.return_value.exclude.return_value.distinct.return_value.exists.return_value = False

    abono = AbonoFaltas(aluno_id=1, data_inicio=datetime.date(2023, 1, 5), data_fim=datetime.date(2023, 1, 10), deferido=True)
    abono.clean()


@pytest.mark.django_db
def test_indeferir_requerimentos_automatizados_ao_cancelar_matricula() -> None:
    aluno = AlunoFactory()
    outro_aluno = AlunoFactory()
    mp = MatriculaPeriodoFactory(aluno=aluno, ano_letivo__ano=2026, periodo_letivo=1)
    procedimento = ProcedimentoMatriculaFactory(
        matricula_periodo=mp,
        tipo=ProcedimentoMatricula.CANCELAMENTO_VOLUNTARIO,
    )

    # Requerimentos automatizados que DEVEM ser indeferidos
    req_trancamento = RequerimentoFactory(aluno=aluno, tipo=Requerimento.TRANCAMENTO_MATRICULA)
    req_prova = RequerimentoFactory(aluno=aluno, tipo=Requerimento.REALIZACAO_PROVA)
    req_disciplina = RequerimentoFactory(aluno=aluno, tipo=Requerimento.MATRICULA_DISCIPLINA)

    # Requerimentos que NÃO devem ser indeferidos pelo procedimento (geridos pela task de renovação)
    req_quebra = RequerimentoFactory(aluno=aluno, tipo=Requerimento.MATRICULA_QUEBRA_REQUISITO)
    req_ch_max = RequerimentoFactory(aluno=aluno, tipo=Requerimento.MATRICULA_QUEBRA_CH_MAX)

    # Requerimento não automatizado
    req_outro = RequerimentoFactory(aluno=aluno, tipo=Requerimento.OUTRO)

    # Requerimento já arquivado
    req_arquivado = RequerimentoFactory(
        aluno=aluno,
        tipo=Requerimento.TRANCAMENTO_MATRICULA,
        deferido=True,
    )
    req_arquivado.situacao = Requerimento.SITUACAO_ARQUIVADO
    req_arquivado.save()

    # Requerimento de outro aluno
    req_outro_aluno = RequerimentoFactory(aluno=outro_aluno, tipo=Requerimento.TRANCAMENTO_MATRICULA)

    mp.indeferir_requerimentos_automatizados_pendentes(procedimento)

    obs_esperada = 'Requerimento indeferido automaticamente devido ao procedimento de Cancelamento Voluntário (2026.1).'
    for req in [req_trancamento, req_prova, req_disciplina]:
        req.refresh_from_db()
        assert req.deferido is False
        assert req.situacao == Requerimento.SITUACAO_ARQUIVADO
        assert req.atendente is None
        assert req.observacao == obs_esperada

    req_quebra.refresh_from_db()
    assert req_quebra.deferido is None
    assert req_quebra.situacao == Requerimento.SITUACAO_EM_ANDAMENTO

    req_ch_max.refresh_from_db()
    assert req_ch_max.deferido is None
    assert req_ch_max.situacao == Requerimento.SITUACAO_EM_ANDAMENTO

    req_outro.refresh_from_db()
    assert req_outro.deferido is None
    assert req_outro.situacao == Requerimento.SITUACAO_EM_ANDAMENTO

    req_arquivado.refresh_from_db()
    assert req_arquivado.deferido is True
    assert req_arquivado.situacao == Requerimento.SITUACAO_ARQUIVADO

    req_outro_aluno.refresh_from_db()
    assert req_outro_aluno.deferido is None
    assert req_outro_aluno.situacao == Requerimento.SITUACAO_EM_ANDAMENTO


@pytest.mark.django_db
@pytest.mark.parametrize(
    ('tipo_procedimento', 'deve_chamar'),
    [
        (ProcedimentoMatricula.CANCELAMENTO_VOLUNTARIO, True),
        (ProcedimentoMatricula.CANCELAMENTO_COMPULSORIO, True),
        (ProcedimentoMatricula.CANCELAMENTO_POR_DUPLICIDADE, True),
        (ProcedimentoMatricula.CANCELAMENTO_POR_DESLIGAMENTO, True),
        (ProcedimentoMatricula.EVASAO, True),
        (ProcedimentoMatricula.JUBILAMENTO, True),
        (ProcedimentoMatricula.TRANCAMENTO_VOLUNTARIO, False),
        (ProcedimentoMatricula.TRANCAMENTO_COMPULSORIO, False),
        (ProcedimentoMatricula.INTERCAMBIO, False),
    ],
)
def test_realizar_procedimento_matricula_chama_indeferimento_apenas_para_cancelamento_vinculo(
    tipo_procedimento: str,
    deve_chamar: bool,
) -> None:
    aluno = AlunoFactory()
    mp = MatriculaPeriodoFactory(aluno=aluno)
    procedimento = ProcedimentoMatricula(
        tipo=tipo_procedimento,
        situacao_matricula_anterior=aluno.situacao,
        matricula_periodo=mp,
        motivo='Teste procedimento',
        data=datetime.date.today(),
    )

    with (
        patch.object(mp, 'indeferir_requerimentos_automatizados_pendentes') as mock_indeferir,
        patch.object(mp, 'instanciar_proxima_matricula_periodo'),
    ):
        mp.realizar_procedimento_matricula(
            procedimento=procedimento,
            situacao_matricula=aluno.situacao,
            situacao_matricula_periodo=mp.situacao,
            situacao_matricula_diario=MatriculaDiario.SITUACAO_CANCELADO,
        )

    if deve_chamar:
        mock_indeferir.assert_called_once_with(procedimento)
    else:
        mock_indeferir.assert_not_called()


@pytest.mark.django_db
def test_requerimento_aproveitamento_estudo_indeferir_atualiza_solicitacoes_filhas_pendentes() -> None:
    req = RequerimentoAproveitamentoEstudoFactory(observacao='Motivo indeferimento')
    outro_req = RequerimentoAproveitamentoEstudoFactory(observacao='Outra obs')

    sol_cadastrada = SolicitacaoAproveitamentoEstudoFactory(
        requerimento=req, situacao=SolicitacaoAproveitamentoEstudo.SITUACAO_CADASTRADA, observacao=None
    )
    sol_solicitada = SolicitacaoAproveitamentoEstudoFactory(
        requerimento=req, situacao=SolicitacaoAproveitamentoEstudo.SITUACAO_SOLICITADA, observacao=''
    )
    sol_em_analise_sem_obs = SolicitacaoAproveitamentoEstudoFactory(
        requerimento=req, situacao=SolicitacaoAproveitamentoEstudo.SITUACAO_EM_ANALISE, observacao='   '
    )
    sol_em_analise_com_obs = SolicitacaoAproveitamentoEstudoFactory(
        requerimento=req,
        situacao=SolicitacaoAproveitamentoEstudo.SITUACAO_EM_ANALISE,
        observacao='Parecer prévio do professor',
    )
    sol_deferida = SolicitacaoAproveitamentoEstudoFactory(
        requerimento=req, situacao=SolicitacaoAproveitamentoEstudo.SITUACAO_DEFERIDA, observacao='Doc aprovado'
    )
    sol_outro_req = SolicitacaoAproveitamentoEstudoFactory(
        requerimento=outro_req, situacao=SolicitacaoAproveitamentoEstudo.SITUACAO_EM_ANALISE, observacao='Outra obs'
    )

    req.indeferir(atendente=None, notificar=False)

    req.refresh_from_db()
    assert req.deferido is False
    assert req.situacao == Requerimento.SITUACAO_ARQUIVADO
    assert req.atendente is None

    # Solicitações sem observação prévia recebem a observação do requerimento
    for sol in [sol_cadastrada, sol_solicitada, sol_em_analise_sem_obs]:
        sol.refresh_from_db()
        assert sol.situacao == SolicitacaoAproveitamentoEstudo.SITUACAO_INDEFERIDA
        assert sol.observacao == 'Motivo indeferimento'

    # Solicitação com observação prévia tem o motivo concatenado preservando a nota
    sol_em_analise_com_obs.refresh_from_db()
    assert sol_em_analise_com_obs.situacao == SolicitacaoAproveitamentoEstudo.SITUACAO_INDEFERIDA
    assert sol_em_analise_com_obs.observacao == 'Parecer prévio do professor\n\nMotivo indeferimento'

    # Solicitação já finalizada não é alterada
    sol_deferida.refresh_from_db()
    assert sol_deferida.situacao == SolicitacaoAproveitamentoEstudo.SITUACAO_DEFERIDA
    assert sol_deferida.observacao == 'Doc aprovado'

    # Solicitação de outro requerimento não é alterada
    sol_outro_req.refresh_from_db()
    assert sol_outro_req.situacao == SolicitacaoAproveitamentoEstudo.SITUACAO_EM_ANALISE
    assert sol_outro_req.observacao == 'Outra obs'


@pytest.mark.django_db
@pytest.mark.parametrize('observacao_vazia', [None, '', '   '])
def test_requerimento_aproveitamento_estudo_indeferir_sem_observacao_nao_sobrescreve_observacoes(
    observacao_vazia: str | None,
) -> None:
    req = RequerimentoAproveitamentoEstudoFactory(observacao=observacao_vazia)

    sol_em_analise = SolicitacaoAproveitamentoEstudoFactory(
        requerimento=req,
        situacao=SolicitacaoAproveitamentoEstudo.SITUACAO_EM_ANALISE,
        observacao='Parecer previo do professor',
    )
    sol_sem_obs = SolicitacaoAproveitamentoEstudoFactory(
        requerimento=req,
        situacao=SolicitacaoAproveitamentoEstudo.SITUACAO_SOLICITADA,
        observacao=None,
    )

    req.indeferir(atendente=None, notificar=False)

    req.refresh_from_db()
    assert req.deferido is False
    assert req.situacao == Requerimento.SITUACAO_ARQUIVADO

    sol_em_analise.refresh_from_db()
    assert sol_em_analise.situacao == SolicitacaoAproveitamentoEstudo.SITUACAO_INDEFERIDA
    assert sol_em_analise.observacao == 'Parecer previo do professor'

    sol_sem_obs.refresh_from_db()
    assert sol_sem_obs.situacao == SolicitacaoAproveitamentoEstudo.SITUACAO_INDEFERIDA
    assert sol_sem_obs.observacao is None


def test_requerimento_aproveitamento_estudo_atualizar_situacao_ignora_se_ja_indeferido() -> None:
    from edu.models.procedimentos import RequerimentoAproveitamentoEstudo

    req = RequerimentoAproveitamentoEstudo(
        situacao=Requerimento.SITUACAO_ARQUIVADO,
        deferido=False,
    )
    with (
        patch.object(req, 'save') as mock_save,
        patch.object(req, 'enviar_email') as mock_email,
    ):
        req.atualizar_situacao()

        mock_save.assert_not_called()
        mock_email.assert_not_called()
        assert req.situacao == Requerimento.SITUACAO_ARQUIVADO
        assert req.deferido is False


@pytest.mark.django_db
def test_aluno_jubilar_chama_indeferimento_na_ultima_matricula_periodo() -> None:
    SituacaoMatriculaFactory(id=SituacaoMatricula.JUBILADO, descricao='Jubilado')
    SituacaoMatriculaPeriodoFactory(id=SituacaoMatriculaPeriodo.JUBILADO, descricao='Jubilado')
    aluno = AlunoFactory()
    mp = MatriculaPeriodoFactory(aluno=aluno)

    with (
        patch.object(aluno, 'get_ultima_matricula_periodo', return_value=mp),
        patch.object(aluno, 'save'),
        patch.object(mp, 'indeferir_requerimentos_automatizados_pendentes') as mock_indeferir,
    ):
        aluno.jubilar(motivo='Jubilamento teste')

        mock_indeferir.assert_called_once()
        procedimento_passado = mock_indeferir.call_args[0][0]
        assert procedimento_passado.tipo == ProcedimentoMatricula.JUBILAMENTO


@pytest.mark.django_db
def test_requerimento_admin_tab_aguardando_minha_avaliacao_exclui_solicitacoes_indeferidas_ou_arquivadas(
    sync_permissions,
) -> None:
    from edu.admin.procedimentos import RequerimentoAdmin

    admin = RequerimentoAdmin(model=Requerimento, admin_site=MagicMock())

    # Docente logado
    servidor = ServidorFactory()
    professor = ProfessorFactory(vinculo=servidor.get_vinculo())
    outro_professor = ProfessorFactory(vinculo=ServidorFactory().get_vinculo())

    request = MagicMock()
    request.user = servidor.get_user()

    # 1. Requerimento em andamento com solicitação aguardando avaliação deste professor -> DEVE RETORNAR
    req_aguardando = RequerimentoAproveitamentoEstudoFactory(situacao=Requerimento.SITUACAO_EM_ANDAMENTO)
    SolicitacaoAproveitamentoEstudoFactory(
        requerimento=req_aguardando,
        avaliador=professor,
        parecer=None,
        situacao=SolicitacaoAproveitamentoEstudo.SITUACAO_EM_ANALISE,
    )

    # 2. Requerimento em andamento com solicitação já indeferida -> NÃO DEVE RETORNAR
    req_solicitacao_indeferida = RequerimentoAproveitamentoEstudoFactory(situacao=Requerimento.SITUACAO_EM_ANDAMENTO)
    SolicitacaoAproveitamentoEstudoFactory(
        requerimento=req_solicitacao_indeferida,
        avaliador=professor,
        parecer=None,
        situacao=SolicitacaoAproveitamentoEstudo.SITUACAO_INDEFERIDA,
    )

    # 3. Requerimento já arquivado com solicitação em análise -> NÃO DEVE RETORNAR
    req_arquivado = RequerimentoAproveitamentoEstudoFactory(situacao=Requerimento.SITUACAO_ARQUIVADO)
    SolicitacaoAproveitamentoEstudoFactory(
        requerimento=req_arquivado,
        avaliador=professor,
        parecer=None,
        situacao=SolicitacaoAproveitamentoEstudo.SITUACAO_EM_ANALISE,
    )

    # 4. Requerimento em andamento com solicitação já avaliada (com parecer) -> NÃO DEVE RETORNAR
    parecer = ParecerAvaliacaoAproveitamentoEstudo.objects.create(descricao='Apto', apto=True, deferido=True)
    req_avaliado = RequerimentoAproveitamentoEstudoFactory(situacao=Requerimento.SITUACAO_EM_ANDAMENTO)
    SolicitacaoAproveitamentoEstudoFactory(
        requerimento=req_avaliado,
        avaliador=professor,
        parecer=parecer,
        situacao=SolicitacaoAproveitamentoEstudo.SITUACAO_DEFERIDA,
    )

    # 5. Requerimento de outro avaliador -> NÃO DEVE RETORNAR
    req_outro_avaliador = RequerimentoAproveitamentoEstudoFactory(situacao=Requerimento.SITUACAO_EM_ANDAMENTO)
    SolicitacaoAproveitamentoEstudoFactory(
        requerimento=req_outro_avaliador,
        avaliador=outro_professor,
        parecer=None,
        situacao=SolicitacaoAproveitamentoEstudo.SITUACAO_EM_ANALISE,
    )

    # Base de requerimentos criados neste teste
    qs_base = Requerimento.objects.filter(
        pk__in=[
            req_aguardando.pk,
            req_solicitacao_indeferida.pk,
            req_arquivado.pk,
            req_avaliado.pk,
            req_outro_avaliador.pk,
        ]
    )
    resultado = admin.tab_aguardando_minha_avaliacao(request, qs_base)

    # Comportamento observável: apenas o requerimento pendente do professor é retornado
    assert set(resultado.values_list('pk', flat=True)) == {req_aguardando.pk}


@pytest.mark.django_db
def test_requerimento_indeferir_agenda_enviar_email_no_commit(django_capture_on_commit_callbacks) -> None:
    req = RequerimentoFactory()
    with (
        patch.object(req, 'enviar_email') as mock_email,
        django_capture_on_commit_callbacks(execute=True),
    ):
        req.indeferir(atendente=None, notificar=True)

    mock_email.assert_called_once()


@pytest.mark.django_db
def test_requerimento_indeferir_com_notificar_false_nao_agenda_enviar_email(django_capture_on_commit_callbacks) -> None:
    req = RequerimentoFactory()
    with (
        patch.object(req, 'enviar_email') as mock_email,
        django_capture_on_commit_callbacks(execute=True),
    ):
        req.indeferir(atendente=None, notificar=False)

    mock_email.assert_not_called()


@pytest.mark.django_db
def test_requerimento_indeferir_em_transacao_revertida_nao_envia_email() -> None:
    req = RequerimentoFactory()
    with patch.object(req, 'enviar_email') as mock_email:

        def _operacao_com_falha() -> None:
            with transaction.atomic():
                req.indeferir(atendente=None, notificar=True)
                raise RuntimeError('Erro simulado forçando rollback')

        with pytest.raises(RuntimeError):
            _operacao_com_falha()

        mock_email.assert_not_called()


@pytest.mark.django_db
def test_requerimento_aproveitamento_estudo_desarquivar_restaura_solicitacoes_nao_finalizadas(
    sync_permissions,
) -> None:
    req = RequerimentoAproveitamentoEstudoFactory(
        situacao=Requerimento.SITUACAO_ARQUIVADO,
        deferido=False,
    )
    professor = ProfessorFactory()
    parecer_inapto = ParecerAvaliacaoAproveitamentoEstudo.objects.create(descricao='Inapto', apto=False, deferido=False)
    parecer_indeferido = ParecerAvaliacaoAproveitamentoEstudo.objects.create(descricao='Indeferido', apto=True, deferido=False)

    sol_sem_avaliador = SolicitacaoAproveitamentoEstudoFactory(
        requerimento=req,
        situacao=SolicitacaoAproveitamentoEstudo.SITUACAO_INDEFERIDA,
        avaliador=None,
        parecer=None,
    )
    sol_com_avaliador_sem_parecer = SolicitacaoAproveitamentoEstudoFactory(
        requerimento=req,
        situacao=SolicitacaoAproveitamentoEstudo.SITUACAO_INDEFERIDA,
        avaliador=professor,
        parecer=None,
    )
    sol_com_avaliador_parecer_inapto = SolicitacaoAproveitamentoEstudoFactory(
        requerimento=req,
        situacao=SolicitacaoAproveitamentoEstudo.SITUACAO_INDEFERIDA,
        avaliador=professor,
        parecer=parecer_inapto,
    )
    sol_finalizada_indeferida = SolicitacaoAproveitamentoEstudoFactory(
        requerimento=req,
        situacao=SolicitacaoAproveitamentoEstudo.SITUACAO_INDEFERIDA,
        avaliador=professor,
        parecer=parecer_indeferido,
    )

    req.desarquivar()

    req.refresh_from_db()
    assert req.situacao == Requerimento.SITUACAO_EM_ANDAMENTO
    assert req.deferido is None
    assert req.termino is None

    sol_sem_avaliador.refresh_from_db()
    assert sol_sem_avaliador.situacao == SolicitacaoAproveitamentoEstudo.SITUACAO_SOLICITADA

    sol_com_avaliador_sem_parecer.refresh_from_db()
    assert sol_com_avaliador_sem_parecer.situacao == SolicitacaoAproveitamentoEstudo.SITUACAO_EM_ANALISE

    sol_com_avaliador_parecer_inapto.refresh_from_db()
    assert sol_com_avaliador_parecer_inapto.situacao == SolicitacaoAproveitamentoEstudo.SITUACAO_EM_ANALISE

    sol_finalizada_indeferida.refresh_from_db()
    assert sol_finalizada_indeferida.situacao == SolicitacaoAproveitamentoEstudo.SITUACAO_INDEFERIDA
