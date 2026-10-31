from __future__ import annotations

import io
from typing import Any
from unittest.mock import patch

import pytest
from django.core.management import call_command

from edu.models import (
    ProcedimentoMatricula,
    Requerimento,
    RequerimentoAproveitamentoEstudo,
    SituacaoMatricula,
    SituacaoMatriculaPeriodo,
    SolicitacaoAproveitamentoEstudo,
)
from edu.tests.factories import (
    AlunoFactory,
    MatriculaPeriodoFactory,
    ProcedimentoMatriculaFactory,
    RequerimentoAproveitamentoEstudoFactory,
    RequerimentoFactory,
    SituacaoMatriculaFactory,
    SituacaoMatriculaPeriodoFactory,
    SolicitacaoAproveitamentoEstudoFactory,
)


@pytest.mark.django_db
class TestEduIndeferirRequerimentosVinculoCancelado:
    def test_dry_run_nao_persiste_alteracoes(self) -> None:
        sit_cancelado = SituacaoMatriculaFactory(pk=SituacaoMatricula.CANCELADO, descricao='Cancelado')
        sit_mp_cancelada = SituacaoMatriculaPeriodoFactory(pk=SituacaoMatriculaPeriodo.CANCELADA, descricao='Cancelada')

        aluno = AlunoFactory(situacao=sit_cancelado)
        mp = MatriculaPeriodoFactory(aluno=aluno, situacao=sit_mp_cancelada, ano_letivo__ano=2026, periodo_letivo=1)
        ProcedimentoMatriculaFactory(
            matricula_periodo=mp,
            tipo=ProcedimentoMatricula.CANCELAMENTO_VOLUNTARIO,
        )

        req_pendente = RequerimentoFactory(
            aluno=aluno,
            tipo=Requerimento.TRANCAMENTO_MATRICULA,
            situacao=Requerimento.SITUACAO_EM_ANDAMENTO,
            deferido=None,
        )

        req_aprov_ja_indeferido = RequerimentoAproveitamentoEstudoFactory(
            aluno=aluno,
            situacao=Requerimento.SITUACAO_ARQUIVADO,
            deferido=False,
        )
        sol_orfa = SolicitacaoAproveitamentoEstudoFactory(
            requerimento=req_aprov_ja_indeferido,
            situacao=SolicitacaoAproveitamentoEstudo.SITUACAO_EM_ANALISE,
        )

        out = io.StringIO()
        call_command('edu_indeferir_requerimentos_vinculo_cancelado', stdout=out)
        output = out.getvalue()

        assert '[DRY-RUN]' in output
        assert 'Requerimentos automatizados pendentes indeferidos: 1' in output
        assert 'Requerimentos já indeferidos com solicitações órfãs higienizadas: 1' in output

        req_pendente.refresh_from_db()
        assert req_pendente.deferido is None
        assert req_pendente.situacao == Requerimento.SITUACAO_EM_ANDAMENTO

        sol_orfa.refresh_from_db()
        assert sol_orfa.situacao == SolicitacaoAproveitamentoEstudo.SITUACAO_EM_ANALISE

    def test_commit_indefere_requerimentos_pendentes_e_solicitacoes_filhas(self) -> None:
        sit_cancelado = SituacaoMatriculaFactory(pk=SituacaoMatricula.CANCELADO, descricao='Cancelado')
        sit_mp_cancelada = SituacaoMatriculaPeriodoFactory(pk=SituacaoMatriculaPeriodo.CANCELADA, descricao='Cancelada')

        aluno = AlunoFactory(situacao=sit_cancelado)
        mp = MatriculaPeriodoFactory(aluno=aluno, situacao=sit_mp_cancelada, ano_letivo__ano=2026, periodo_letivo=1)
        ProcedimentoMatriculaFactory(
            matricula_periodo=mp,
            tipo=ProcedimentoMatricula.CANCELAMENTO_VOLUNTARIO,
        )

        req_trancamento = RequerimentoFactory(
            aluno=aluno,
            tipo=Requerimento.TRANCAMENTO_MATRICULA,
            situacao=Requerimento.SITUACAO_EM_ANDAMENTO,
            deferido=None,
        )

        req_aproveitamento = RequerimentoAproveitamentoEstudoFactory(
            aluno=aluno,
            situacao=Requerimento.SITUACAO_EM_ANDAMENTO,
            deferido=None,
        )
        solicitacao_filha = SolicitacaoAproveitamentoEstudoFactory(
            requerimento=req_aproveitamento,
            situacao=SolicitacaoAproveitamentoEstudo.SITUACAO_SOLICITADA,
            observacao='Dúvida na ementa',
        )

        out = io.StringIO()
        call_command('edu_indeferir_requerimentos_vinculo_cancelado', commit=True, stdout=out)
        output = out.getvalue()

        assert '[SUCESSO]' in output
        obs_esperada = 'Requerimento indeferido automaticamente devido ao procedimento de Cancelamento Voluntário (2026.1).'

        req_trancamento.refresh_from_db()
        assert req_trancamento.deferido is False
        assert req_trancamento.situacao == Requerimento.SITUACAO_ARQUIVADO
        assert req_trancamento.observacao == obs_esperada

        req_aproveitamento.refresh_from_db()
        assert req_aproveitamento.deferido is False
        assert req_aproveitamento.situacao == Requerimento.SITUACAO_ARQUIVADO
        assert req_aproveitamento.observacao == obs_esperada

        solicitacao_filha.refresh_from_db()
        assert solicitacao_filha.situacao == SolicitacaoAproveitamentoEstudo.SITUACAO_INDEFERIDA
        assert solicitacao_filha.observacao == f'Dúvida na ementa\n\n{obs_esperada}'

    def test_ignora_aluno_reintegrado_ou_com_ultimo_procedimento_nao_cancelamento(self) -> None:
        sit_matriculado = SituacaoMatriculaFactory(pk=SituacaoMatricula.MATRICULADO, descricao='Matriculado')
        sit_mp_aberto = SituacaoMatriculaPeriodoFactory(pk=SituacaoMatriculaPeriodo.EM_ABERTO, descricao='Em Aberto')

        aluno = AlunoFactory(situacao=sit_matriculado)
        mp = MatriculaPeriodoFactory(aluno=aluno, situacao=sit_mp_aberto, ano_letivo__ano=2026, periodo_letivo=1)

        # Procedimento de cancelamento no passado
        ProcedimentoMatriculaFactory(
            matricula_periodo=mp,
            tipo=ProcedimentoMatricula.CANCELAMENTO_VOLUNTARIO,
        )
        # Procedimento de reintegração posterior (último procedimento)
        ProcedimentoMatriculaFactory(
            matricula_periodo=mp,
            tipo=ProcedimentoMatricula.REINTEGRACAO,
        )

        req_ativo = RequerimentoFactory(
            aluno=aluno,
            tipo=Requerimento.TRANCAMENTO_MATRICULA,
            situacao=Requerimento.SITUACAO_EM_ANDAMENTO,
            deferido=None,
        )

        out = io.StringIO()
        call_command('edu_indeferir_requerimentos_vinculo_cancelado', commit=True, stdout=out)

        req_ativo.refresh_from_db()
        assert req_ativo.deferido is None
        assert req_ativo.situacao == Requerimento.SITUACAO_EM_ANDAMENTO

    def test_ignora_tipos_excluidos_e_requerimentos_nao_automatizados(self) -> None:
        sit_cancelado = SituacaoMatriculaFactory(pk=SituacaoMatricula.CANCELADO, descricao='Cancelado')
        sit_mp_cancelada = SituacaoMatriculaPeriodoFactory(pk=SituacaoMatriculaPeriodo.CANCELADA, descricao='Cancelada')

        aluno = AlunoFactory(situacao=sit_cancelado)
        mp = MatriculaPeriodoFactory(aluno=aluno, situacao=sit_mp_cancelada, ano_letivo__ano=2026, periodo_letivo=1)
        ProcedimentoMatriculaFactory(
            matricula_periodo=mp,
            tipo=ProcedimentoMatricula.CANCELAMENTO_VOLUNTARIO,
        )

        req_quebra = RequerimentoFactory(
            aluno=aluno,
            tipo=Requerimento.MATRICULA_QUEBRA_REQUISITO,
            situacao=Requerimento.SITUACAO_EM_ANDAMENTO,
            deferido=None,
        )
        req_ch_max = RequerimentoFactory(
            aluno=aluno,
            tipo=Requerimento.MATRICULA_QUEBRA_CH_MAX,
            situacao=Requerimento.SITUACAO_EM_ANDAMENTO,
            deferido=None,
        )
        req_outro = RequerimentoFactory(
            aluno=aluno,
            tipo=Requerimento.OUTRO,
            situacao=Requerimento.SITUACAO_EM_ANDAMENTO,
            deferido=None,
        )

        call_command('edu_indeferir_requerimentos_vinculo_cancelado', commit=True)

        req_quebra.refresh_from_db()
        assert req_quebra.deferido is None
        assert req_quebra.situacao == Requerimento.SITUACAO_EM_ANDAMENTO

        req_ch_max.refresh_from_db()
        assert req_ch_max.deferido is None
        assert req_ch_max.situacao == Requerimento.SITUACAO_EM_ANDAMENTO

        req_outro.refresh_from_db()
        assert req_outro.deferido is None
        assert req_outro.situacao == Requerimento.SITUACAO_EM_ANDAMENTO

    def test_higieniza_solicitacoes_orfas_de_requerimento_aproveitamento_ja_indeferido(self) -> None:
        req_ja_indeferido = RequerimentoAproveitamentoEstudoFactory(
            situacao=Requerimento.SITUACAO_ARQUIVADO,
            deferido=False,
            observacao='Indeferimento manual anterior',
        )

        sol_sem_obs = SolicitacaoAproveitamentoEstudoFactory(
            requerimento=req_ja_indeferido,
            situacao=SolicitacaoAproveitamentoEstudo.SITUACAO_CADASTRADA,
            observacao='',
        )
        sol_com_obs = SolicitacaoAproveitamentoEstudoFactory(
            requerimento=req_ja_indeferido,
            situacao=SolicitacaoAproveitamentoEstudo.SITUACAO_EM_ANALISE,
            observacao='Comentário docente',
        )
        sol_deferida = SolicitacaoAproveitamentoEstudoFactory(
            requerimento=req_ja_indeferido,
            situacao=SolicitacaoAproveitamentoEstudo.SITUACAO_DEFERIDA,
            observacao='Aprovada',
        )

        call_command('edu_indeferir_requerimentos_vinculo_cancelado', commit=True)

        sol_sem_obs.refresh_from_db()
        assert sol_sem_obs.situacao == SolicitacaoAproveitamentoEstudo.SITUACAO_INDEFERIDA
        assert sol_sem_obs.observacao == 'Indeferimento manual anterior'

        sol_com_obs.refresh_from_db()
        assert sol_com_obs.situacao == SolicitacaoAproveitamentoEstudo.SITUACAO_INDEFERIDA
        assert sol_com_obs.observacao == 'Comentário docente\n\nIndeferimento manual anterior'

        sol_deferida.refresh_from_db()
        assert sol_deferida.situacao == SolicitacaoAproveitamentoEstudo.SITUACAO_DEFERIDA
        assert sol_deferida.observacao == 'Aprovada'

    def test_flag_notificar_controla_envio_de_email(
        self,
        django_capture_on_commit_callbacks: Any,
    ) -> None:
        sit_cancelado = SituacaoMatriculaFactory(pk=SituacaoMatricula.CANCELADO, descricao='Cancelado')
        sit_mp_cancelada = SituacaoMatriculaPeriodoFactory(pk=SituacaoMatriculaPeriodo.CANCELADA, descricao='Cancelada')

        aluno = AlunoFactory(situacao=sit_cancelado)
        mp = MatriculaPeriodoFactory(aluno=aluno, situacao=sit_mp_cancelada)
        ProcedimentoMatriculaFactory(
            matricula_periodo=mp,
            tipo=ProcedimentoMatricula.CANCELAMENTO_VOLUNTARIO,
        )

        req1 = RequerimentoFactory(
            aluno=aluno,
            tipo=Requerimento.TRANCAMENTO_MATRICULA,
            situacao=Requerimento.SITUACAO_EM_ANDAMENTO,
            deferido=None,
        )

        # Sem --notificar (padrão): não agenda envio de e-mail
        with (
            patch.object(Requerimento, 'enviar_email') as mock_email_padrao,
            django_capture_on_commit_callbacks(execute=True),
        ):
            call_command('edu_indeferir_requerimentos_vinculo_cancelado', commit=True, requerimento=req1.id)

        mock_email_padrao.assert_not_called()

        # Com --notificar: agenda envio de e-mail
        req2 = RequerimentoFactory(
            aluno=aluno,
            tipo=Requerimento.TRANCAMENTO_MATRICULA,
            situacao=Requerimento.SITUACAO_EM_ANDAMENTO,
            deferido=None,
        )
        with (
            patch.object(Requerimento, 'enviar_email') as mock_email_notif,
            django_capture_on_commit_callbacks(execute=True),
        ):
            call_command(
                'edu_indeferir_requerimentos_vinculo_cancelado',
                commit=True,
                notificar=True,
                requerimento=req2.id,
            )

        mock_email_notif.assert_called()

    def test_filtros_por_aluno_e_requerimento(self) -> None:
        sit_cancelado = SituacaoMatriculaFactory(pk=SituacaoMatricula.CANCELADO, descricao='Cancelado')
        sit_mp_cancelada = SituacaoMatriculaPeriodoFactory(pk=SituacaoMatriculaPeriodo.CANCELADA, descricao='Cancelada')

        aluno_a = AlunoFactory(situacao=sit_cancelado)
        mp_a = MatriculaPeriodoFactory(aluno=aluno_a, situacao=sit_mp_cancelada)
        ProcedimentoMatriculaFactory(matricula_periodo=mp_a, tipo=ProcedimentoMatricula.CANCELAMENTO_VOLUNTARIO)

        aluno_b = AlunoFactory(situacao=sit_cancelado)
        mp_b = MatriculaPeriodoFactory(aluno=aluno_b, situacao=sit_mp_cancelada)
        ProcedimentoMatriculaFactory(matricula_periodo=mp_b, tipo=ProcedimentoMatricula.CANCELAMENTO_VOLUNTARIO)

        req_a = RequerimentoFactory(aluno=aluno_a, tipo=Requerimento.TRANCAMENTO_MATRICULA)
        req_b = RequerimentoFactory(aluno=aluno_b, tipo=Requerimento.TRANCAMENTO_MATRICULA)

        call_command(
            'edu_indeferir_requerimentos_vinculo_cancelado',
            commit=True,
            aluno=aluno_a.matricula,
        )

        req_a.refresh_from_db()
        assert req_a.deferido is False

        req_b.refresh_from_db()
        assert req_b.deferido is None
