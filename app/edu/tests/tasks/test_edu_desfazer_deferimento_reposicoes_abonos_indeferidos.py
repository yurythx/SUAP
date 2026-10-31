from __future__ import annotations

import datetime
import io

import pytest
from django.core.management import call_command

from comum.tests.factories import UserFactory
from edu.models import AbonoFaltas, SolicitacaoReposicaoAtividade
from edu.models.diarios import ConfiguracaoAvaliacao, ItemConfiguracaoAvaliacao
from edu.tests.factories import AlunoFactory, DiarioFactory


@pytest.mark.django_db
class TestEduDesfazerDeferimentoReposicoesAbonosIndeferidos:
    @pytest.fixture
    def cenario_solicitacao(self):
        hoje = datetime.date.today()
        aluno = AlunoFactory()
        diario = DiarioFactory()
        config = ConfiguracaoAvaliacao.objects.create(diario=diario, etapa=1)
        item = ItemConfiguracaoAvaliacao.objects.create(configuracao_avaliacao=config, sigla='A1')
        avaliador = UserFactory()

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
            avaliador=avaliador,
            observacao='Agendada previamente',
        )
        return {
            'aluno': aluno,
            'abono': abono,
            'item': item,
            'solicitacao': solicitacao,
            'hoje': hoje,
            'avaliador': avaliador,
        }

    def test_dry_run_nao_persiste_alteracoes(self, cenario_solicitacao) -> None:
        solicitacao = cenario_solicitacao['solicitacao']
        hoje = cenario_solicitacao['hoje']
        avaliador = cenario_solicitacao['avaliador']

        out = io.StringIO()
        call_command('edu_desfazer_deferimento_reposicoes_abonos_indeferidos', stdout=out)
        output = out.getvalue()

        solicitacao.refresh_from_db()
        assert solicitacao.deferida is True
        assert solicitacao.data_reposicao == hoje
        assert solicitacao.avaliador == avaliador
        assert solicitacao.observacao == 'Agendada previamente'

        assert 'DIAGNÓSTICO (dry-run, somente leitura)' in output
        assert f'Solicitação #{solicitacao.id}' in output
        assert '- Total de solicitações afetadas: 1' in output
        assert '[DRY-RUN] Nenhuma alteração foi realizada' in output

    def test_commit_desfaz_deferimento_de_solicitacoes_de_abonos_indeferidos(self, cenario_solicitacao) -> None:
        solicitacao = cenario_solicitacao['solicitacao']

        out = io.StringIO()
        call_command('edu_desfazer_deferimento_reposicoes_abonos_indeferidos', commit=True, stdout=out)
        output = out.getvalue()

        solicitacao.refresh_from_db()
        assert solicitacao.deferida is None
        assert solicitacao.data_reposicao is None
        assert solicitacao.avaliador is None
        assert solicitacao.observacao is None

        assert 'EXECUÇÃO COM COMMIT' in output
        assert '- Total de solicitações afetadas: 1' in output
        assert '[SUCESSO] Todas as alterações foram concluídas com sucesso' in output

    def test_nao_modifica_solicitacoes_de_abonos_deferidos_ou_pendentes(self) -> None:
        hoje = datetime.date.today()
        aluno = AlunoFactory()
        diario = DiarioFactory()
        config = ConfiguracaoAvaliacao.objects.create(diario=diario, etapa=1)
        item = ItemConfiguracaoAvaliacao.objects.create(configuracao_avaliacao=config, sigla='A1')

        abono_deferido = AbonoFaltas.objects.create(
            aluno=aluno,
            data_inicio=hoje,
            data_fim=hoje,
            deferido=True,
        )
        sol_deferido = SolicitacaoReposicaoAtividade.objects.create(
            abono_faltas=abono_deferido,
            item_configuracao_avaliacao=item,
            deferida=True,
            data_reposicao=hoje,
        )

        abono_pendente = AbonoFaltas.objects.create(
            aluno=aluno,
            data_inicio=hoje,
            data_fim=hoje,
            deferido=None,
        )
        sol_pendente = SolicitacaoReposicaoAtividade.objects.create(
            abono_faltas=abono_pendente,
            item_configuracao_avaliacao=item,
            deferida=True,
            data_reposicao=hoje,
        )

        out = io.StringIO()
        call_command('edu_desfazer_deferimento_reposicoes_abonos_indeferidos', commit=True, stdout=out)
        output = out.getvalue()

        sol_deferido.refresh_from_db()
        sol_pendente.refresh_from_db()

        assert sol_deferido.deferida is True
        assert sol_deferido.data_reposicao == hoje
        assert sol_pendente.deferida is True
        assert sol_pendente.data_reposicao == hoje

        assert '- Total de solicitações afetadas: 0' in output
        assert 'Nenhuma solicitação de reposição deferida com abono indeferido encontrada.' in output

    def test_filtro_por_abono_especifico(self, cenario_solicitacao) -> None:
        hoje = cenario_solicitacao['hoje']
        aluno2 = AlunoFactory()
        item = cenario_solicitacao['item']
        solicitacao1 = cenario_solicitacao['solicitacao']
        abono1 = cenario_solicitacao['abono']

        abono2 = AbonoFaltas.objects.create(
            aluno=aluno2,
            data_inicio=hoje,
            data_fim=hoje,
            deferido=False,
        )
        solicitacao2 = SolicitacaoReposicaoAtividade.objects.create(
            abono_faltas=abono2,
            item_configuracao_avaliacao=item,
            deferida=True,
            data_reposicao=hoje,
        )

        out = io.StringIO()
        call_command('edu_desfazer_deferimento_reposicoes_abonos_indeferidos', abono=abono1.id, commit=True, stdout=out)

        solicitacao1.refresh_from_db()
        solicitacao2.refresh_from_db()

        assert solicitacao1.deferida is None
        assert solicitacao2.deferida is True

    def test_filtro_por_matricula_aluno(self, cenario_solicitacao) -> None:
        hoje = cenario_solicitacao['hoje']
        aluno2 = AlunoFactory()
        item = cenario_solicitacao['item']
        solicitacao1 = cenario_solicitacao['solicitacao']
        aluno1 = cenario_solicitacao['aluno']

        abono2 = AbonoFaltas.objects.create(
            aluno=aluno2,
            data_inicio=hoje,
            data_fim=hoje,
            deferido=False,
        )
        solicitacao2 = SolicitacaoReposicaoAtividade.objects.create(
            abono_faltas=abono2,
            item_configuracao_avaliacao=item,
            deferida=True,
            data_reposicao=hoje,
        )

        out = io.StringIO()
        call_command('edu_desfazer_deferimento_reposicoes_abonos_indeferidos', aluno=aluno1.matricula, commit=True, stdout=out)

        solicitacao1.refresh_from_db()
        solicitacao2.refresh_from_db()

        assert solicitacao1.deferida is None
        assert solicitacao2.deferida is True
