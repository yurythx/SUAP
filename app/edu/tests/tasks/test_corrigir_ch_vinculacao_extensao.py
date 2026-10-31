from __future__ import annotations

import datetime
import io
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from django.core.management import call_command

from edu.management.commands.edu_corrigir_ch_vinculacao_extensao import Command
from edu.models import Diario, MatriculaDiario, VinculacaoAtividadeExtensao
from edu.tests.factories import (
    AlunoFactory,
    AtividadeCurricularExtensaoFactory,
    DiarioFactory,
    MatriculaDiarioFactory,
    MatriculaPeriodoFactory,
    VinculacaoAtividadeExtensaoFactory,
)


class TestCorrigirChVinculacaoExtensaoLogicaPura:
    """Testes rápidos de lógica de cálculo e ordenação sem necessidade de banco de dados."""

    def test_ordenar_vinculacoes_prioriza_homologadas_e_ordem_cronologica(self) -> None:
        v_pendente = SimpleNamespace(homologada=None, data_homologacao=None, id=10)
        v_antiga = SimpleNamespace(homologada=True, data_homologacao=datetime.datetime(2025, 1, 10), id=2)
        v_recente = SimpleNamespace(homologada=True, data_homologacao=datetime.datetime(2025, 5, 20), id=1)

        ordenadas = Command._ordenar_vinculacoes([v_pendente, v_recente, v_antiga])
        assert ordenadas == [v_antiga, v_recente, v_pendente]

    def test_calcular_ajustes_vinculacao_unica_excedente(self) -> None:
        v1 = SimpleNamespace(carga_horaria=30, id=1)
        ajustes = Command._calcular_ajustes_matricula_diario([v1], ch_exigida=15)  # type: ignore[list-item]

        assert len(ajustes) == 1
        assert ajustes[0]['vinculacao'] == v1
        assert ajustes[0]['ch_anterior'] == 30
        assert ajustes[0]['ch_nova'] == 15
        assert ajustes[0]['remover'] is False

    def test_calcular_ajustes_multiplas_vinculacoes(self) -> None:
        v1 = SimpleNamespace(carga_horaria=15, id=1)
        v2 = SimpleNamespace(carga_horaria=15, id=2)
        ajustes = Command._calcular_ajustes_matricula_diario([v1, v2], ch_exigida=20)  # type: ignore[list-item]

        # v1 consome 15h dos 20h exigidos (sobrando 5h para v2)
        assert len(ajustes) == 1
        assert ajustes[0]['vinculacao'] == v2
        assert ajustes[0]['ch_anterior'] == 15
        assert ajustes[0]['ch_nova'] == 5
        assert ajustes[0]['remover'] is False

    def test_calcular_ajustes_segunda_vinculacao_com_saldo_zero_deve_remover(self) -> None:
        v1 = SimpleNamespace(carga_horaria=15, id=1)
        v2 = SimpleNamespace(carga_horaria=10, id=2)
        ajustes = Command._calcular_ajustes_matricula_diario([v1, v2], ch_exigida=15)  # type: ignore[list-item]

        # v1 já preenche as 15h; v2 fica com saldo 0h e deve ser removida
        assert len(ajustes) == 1
        assert ajustes[0]['vinculacao'] == v2
        assert ajustes[0]['ch_anterior'] == 10
        assert ajustes[0]['ch_nova'] == 0
        assert ajustes[0]['remover'] is True

    def test_calcular_ajustes_sem_excesso_retorna_vazio(self) -> None:
        v1 = SimpleNamespace(carga_horaria=10, id=1)
        v2 = SimpleNamespace(carga_horaria=5, id=2)
        ajustes = Command._calcular_ajustes_matricula_diario([v1, v2], ch_exigida=20)  # type: ignore[list-item]

        assert ajustes == []

    def test_executar_ajustes_dry_run_nao_altera_objetos(self) -> None:
        v1 = MagicMock(carga_horaria=30, atividade_extensao_id=100)
        cmd = Command()
        ajustes = [{'vinculacao': v1, 'ch_anterior': 30, 'ch_nova': 15, 'remover': False}]

        atividades = cmd._executar_ajustes(ajustes, commit=False)
        assert atividades == {100}
        v1.save.assert_not_called()
        v1.delete.assert_not_called()

    def test_executar_ajustes_commit_salva_e_remove(self) -> None:
        from unittest.mock import patch

        v1 = MagicMock(carga_horaria=30, atividade_extensao_id=100)
        v2 = MagicMock(carga_horaria=10, atividade_extensao_id=200)
        cmd = Command()
        ajustes = [
            {'vinculacao': v1, 'ch_anterior': 30, 'ch_nova': 15, 'remover': False},
            {'vinculacao': v2, 'ch_anterior': 10, 'ch_nova': 0, 'remover': True},
        ]

        mock_atv1 = MagicMock()
        mock_atv2 = MagicMock()
        with patch('edu.management.commands.edu_corrigir_ch_vinculacao_extensao.AtividadeCurricularExtensao.objects.filter') as mock_filter:
            mock_filter.return_value = [mock_atv1, mock_atv2]
            atividades = cmd._executar_ajustes(ajustes, commit=True)

        assert atividades == {100, 200}
        assert v1.carga_horaria == 15
        v1.save.assert_called_once()
        v2.delete.assert_called_once()
        mock_atv1.recalcular_carga_horaria_vinculada.assert_called_once_with(commit=True)
        mock_atv2.recalcular_carga_horaria_vinculada.assert_called_once_with(commit=True)


@pytest.mark.django_db
class TestCorrigirChVinculacaoExtensaoBanco:
    @staticmethod
    def _criar_matricula_diario(diario: Diario, situacao: int = MatriculaDiario.SITUACAO_CURSANDO) -> MatriculaDiario:
        aluno = AlunoFactory(
            matriz=diario.componente_curricular.matriz,
            curso_campus=diario.turma.curso_campus,
        )
        mp = MatriculaPeriodoFactory(aluno=aluno)
        return MatriculaDiarioFactory(diario=diario, matricula_periodo=mp, situacao=situacao)

    def test_identificar_e_corrigir_vinculacao_unica_excedente(self, sync_permissions: Any) -> None:
        diario = DiarioFactory(
            componente_curricular__ch_extensao=15,
            componente_curricular__qtd_avaliacoes=0,
        )
        md = self._criar_matricula_diario(diario)
        atv = AtividadeCurricularExtensaoFactory(
            matricula_periodo=md.matricula_periodo,
            carga_horaria=50,
            requer_distribuicao_ch=True,
            aprovada=True,
        )
        vinc = VinculacaoAtividadeExtensaoFactory(
            matricula_diario=md,
            atividade_extensao=atv,
            carga_horaria=30,
            homologada=True,
        )
        atv.recalcular_carga_horaria_vinculada(commit=True)
        assert atv.carga_horaria_vinculada == 30

        # 1. Modo dry-run (sem --commit)
        out_dry = io.StringIO()
        call_command('edu_corrigir_ch_vinculacao_extensao', stdout=out_dry)
        conteudo_dry = out_dry.getvalue()

        assert f'Matrícula Diário: {md.id}' in conteudo_dry
        assert 'CH Exigida pela Disciplina: 15h' in conteudo_dry
        assert 'CH Vinculada Atual: 30h (Excesso: 15h)' in conteudo_dry
        assert f'Vinculação #{vinc.id} [Homologada] | Atividade #{atv.id}' in conteudo_dry
        assert f'/edu/atividadecurricularextensao/{atv.id}/distribuir/' in conteudo_dry
        assert '30h -> 15h (liberando 15h)' in conteudo_dry
        assert '[DRY-RUN]' in conteudo_dry

        vinc.refresh_from_db()
        atv.refresh_from_db()
        assert vinc.carga_horaria == 30
        assert atv.carga_horaria_vinculada == 30

        # 2. Modo com --commit
        out_commit = io.StringIO()
        call_command('edu_corrigir_ch_vinculacao_extensao', '--commit', stdout=out_commit)
        conteudo_commit = out_commit.getvalue()

        assert '[SUCESSO]' in conteudo_commit
        vinc.refresh_from_db()
        atv.refresh_from_db()
        assert vinc.carga_horaria == 15
        assert atv.carga_horaria_vinculada == 15
        assert atv.get_ch_nao_vinculada() == 35

    def test_multiplas_vinculacoes_homologadas_no_mesmo_diario(self, sync_permissions: Any) -> None:
        diario = DiarioFactory(
            componente_curricular__ch_extensao=20,
            componente_curricular__qtd_avaliacoes=0,
        )
        md = self._criar_matricula_diario(diario)

        atv1 = AtividadeCurricularExtensaoFactory(
            matricula_periodo=md.matricula_periodo,
            carga_horaria=30,
            requer_distribuicao_ch=True,
            aprovada=True,
        )
        vinc1 = VinculacaoAtividadeExtensaoFactory(
            matricula_diario=md,
            atividade_extensao=atv1,
            carga_horaria=15,
            homologada=True,
        )
        atv1.recalcular_carga_horaria_vinculada(commit=True)

        atv2 = AtividadeCurricularExtensaoFactory(
            matricula_periodo=md.matricula_periodo,
            carga_horaria=30,
            requer_distribuicao_ch=True,
            aprovada=True,
        )
        vinc2 = VinculacaoAtividadeExtensaoFactory(
            matricula_diario=md,
            atividade_extensao=atv2,
            carga_horaria=15,
            homologada=True,
        )
        atv2.recalcular_carga_horaria_vinculada(commit=True)

        # Total atual = 15 + 15 = 30h > 20h exigidas
        out = io.StringIO()
        call_command('edu_corrigir_ch_vinculacao_extensao', '--commit', stdout=out)

        vinc1.refresh_from_db()
        vinc2.refresh_from_db()
        atv1.refresh_from_db()
        atv2.refresh_from_db()

        # Primeira vinculação mantém 15h, segunda vinculação reduz para 5h (totalizando 20h)
        assert vinc1.carga_horaria == 15
        assert vinc2.carga_horaria == 5
        assert atv1.carga_horaria_vinculada == 15
        assert atv2.carga_horaria_vinculada == 5

    def test_segunda_vinculacao_zerada_e_removida_com_commit(self, sync_permissions: Any) -> None:
        diario = DiarioFactory(
            componente_curricular__ch_extensao=15,
            componente_curricular__qtd_avaliacoes=0,
        )
        md = self._criar_matricula_diario(diario)

        atv1 = AtividadeCurricularExtensaoFactory(
            matricula_periodo=md.matricula_periodo,
            carga_horaria=20,
            requer_distribuicao_ch=True,
            aprovada=True,
        )
        vinc1 = VinculacaoAtividadeExtensaoFactory(
            matricula_diario=md,
            atividade_extensao=atv1,
            carga_horaria=15,
            homologada=True,
        )
        atv1.recalcular_carga_horaria_vinculada(commit=True)

        atv2 = AtividadeCurricularExtensaoFactory(
            matricula_periodo=md.matricula_periodo,
            carga_horaria=20,
            requer_distribuicao_ch=True,
            aprovada=True,
        )
        vinc2 = VinculacaoAtividadeExtensaoFactory(
            matricula_diario=md,
            atividade_extensao=atv2,
            carga_horaria=10,
            homologada=True,
        )
        atv2.recalcular_carga_horaria_vinculada(commit=True)
        assert atv2.carga_horaria_vinculada == 10

        out = io.StringIO()
        call_command('edu_corrigir_ch_vinculacao_extensao', '--commit', stdout=out)

        vinc1.refresh_from_db()
        assert vinc1.carga_horaria == 15
        assert not VinculacaoAtividadeExtensao.objects.filter(pk=vinc2.pk).exists()

        atv2.refresh_from_db()
        assert atv2.carga_horaria_vinculada == 0
        assert atv2.get_ch_nao_vinculada() == 20

    def test_filtro_incluir_pendentes(self, sync_permissions: Any) -> None:
        diario = DiarioFactory(
            componente_curricular__ch_extensao=10,
            componente_curricular__qtd_avaliacoes=0,
        )
        md = self._criar_matricula_diario(diario)
        atv = AtividadeCurricularExtensaoFactory(
            matricula_periodo=md.matricula_periodo,
            carga_horaria=30,
            requer_distribuicao_ch=True,
            aprovada=True,
        )
        vinc_pendente = VinculacaoAtividadeExtensaoFactory(
            matricula_diario=md,
            atividade_extensao=atv,
            carga_horaria=25,
            homologada=None,
        )
        atv.recalcular_carga_horaria_vinculada(commit=True)

        # Sem --incluir-pendentes: ignora
        out_padrao = io.StringIO()
        call_command('edu_corrigir_ch_vinculacao_extensao', stdout=out_padrao)
        assert 'Matrículas em diário com excesso: 0' in out_padrao.getvalue()

        # Com --incluir-pendentes: identifica e corrige
        out_pendente = io.StringIO()
        call_command('edu_corrigir_ch_vinculacao_extensao', '--incluir-pendentes', '--commit', stdout=out_pendente)
        assert 'Matrículas em diário com excesso: 1' in out_pendente.getvalue()
        assert '25h -> 10h (liberando 15h)' in out_pendente.getvalue()

        vinc_pendente.refresh_from_db()
        atv.refresh_from_db()
        assert vinc_pendente.carga_horaria == 10
        assert atv.carga_horaria_vinculada == 10

    def test_filtro_por_atividade(self, sync_permissions: Any) -> None:
        diario1 = DiarioFactory(componente_curricular__ch_extensao=10, componente_curricular__qtd_avaliacoes=0)
        md1 = self._criar_matricula_diario(diario1)
        atv1 = AtividadeCurricularExtensaoFactory(matricula_periodo=md1.matricula_periodo, carga_horaria=30, requer_distribuicao_ch=True)
        vinc1 = VinculacaoAtividadeExtensaoFactory(matricula_diario=md1, atividade_extensao=atv1, carga_horaria=20, homologada=True)

        diario2 = DiarioFactory(componente_curricular__ch_extensao=10, componente_curricular__qtd_avaliacoes=0)
        md2 = self._criar_matricula_diario(diario2)
        atv2 = AtividadeCurricularExtensaoFactory(matricula_periodo=md2.matricula_periodo, carga_horaria=30, requer_distribuicao_ch=True)
        vinc2 = VinculacaoAtividadeExtensaoFactory(matricula_diario=md2, atividade_extensao=atv2, carga_horaria=20, homologada=True)

        out = io.StringIO()
        call_command('edu_corrigir_ch_vinculacao_extensao', '--atividade', str(atv1.pk), '--commit', stdout=out)

        vinc1.refresh_from_db()
        vinc2.refresh_from_db()
        assert vinc1.carga_horaria == 10
        assert vinc2.carga_horaria == 20

    def test_diario_dentro_do_limite_nao_e_modificado(self, sync_permissions: Any) -> None:
        diario = DiarioFactory(componente_curricular__ch_extensao=30, componente_curricular__qtd_avaliacoes=0)
        md = self._criar_matricula_diario(diario)
        atv = AtividadeCurricularExtensaoFactory(matricula_periodo=md.matricula_periodo, carga_horaria=30, requer_distribuicao_ch=True)
        vinc = VinculacaoAtividadeExtensaoFactory(matricula_diario=md, atividade_extensao=atv, carga_horaria=20, homologada=True)

        out = io.StringIO()
        call_command('edu_corrigir_ch_vinculacao_extensao', '--commit', stdout=out)
        assert 'Matrículas em diário com excesso: 0' in out.getvalue()

        vinc.refresh_from_db()
        assert vinc.carga_horaria == 20
