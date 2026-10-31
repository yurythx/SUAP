"""Serviço de comparação de projetos: % de evolução e indicadores de prazo."""

from __future__ import annotations

from datetime import date

from gerenciador_projetos.enums import SituacaoTarefa
from gerenciador_projetos.portfolio import StatusPrazo, indicadores, progresso_por_projeto, projetos_visiveis
from gerenciador_projetos.tests.factories import ProjetoFactory, TarefaFactory


class TestProgresso:
    def test_media_das_raizes_ignora_cancelada(self):
        projeto = ProjetoFactory(criado_por=self.user_admin)
        com_subtarefas = TarefaFactory(projeto=projeto, criado_por=self.user_admin)
        TarefaFactory(projeto=projeto, criado_por=self.user_admin, tarefa_pai=com_subtarefas, data_conclusao=date(2026, 10, 1))
        TarefaFactory(projeto=projeto, criado_por=self.user_admin, tarefa_pai=com_subtarefas)
        TarefaFactory(projeto=projeto, criado_por=self.user_admin, situacao=SituacaoTarefa.CONCLUIDA)
        TarefaFactory(projeto=projeto, criado_por=self.user_admin, situacao=SituacaoTarefa.CANCELADA)
        vazio = ProjetoFactory(criado_por=self.user_admin)

        assert progresso_por_projeto([projeto, vazio]) == {projeto.pk: 75.0, vazio.pk: 0}
        assert projeto.total_progresso_automatico() == '75'


HOJE = date(2026, 10, 19)


class TestIndicadores:
    def test_contagens_prazo_e_join_da_equipe_nao_dobra(self):
        projeto = ProjetoFactory(criado_por=self.user_admin, data_conclusao_estimada=date(2026, 10, 1))
        projeto.gerentes.add(self.user_admin)
        projeto.membros.add(self.user_admin)
        TarefaFactory(projeto=projeto, criado_por=self.user_admin, data_inicio=date(2026, 9, 1), data_conclusao_estimada=date(2026, 10, 10))
        TarefaFactory(projeto=projeto, criado_por=self.user_admin, data_conclusao_estimada=date(2026, 10, 25))
        TarefaFactory(projeto=projeto, criado_por=self.user_admin, situacao=SituacaoTarefa.CONCLUIDA, data_conclusao_estimada=date(2026, 10, 10))
        vazio = ProjetoFactory(criado_por=self.user_admin)
        vazio.gerentes.add(self.user_admin)

        painel = {i.projeto.pk: i for i in indicadores(projetos_visiveis(self.user_admin), HOJE)}

        assert painel[projeto.pk].por_situacao[SituacaoTarefa.ABERTA] == 2
        assert painel[projeto.pk].por_situacao[SituacaoTarefa.CONCLUIDA] == 1
        assert (painel[projeto.pk].atrasadas, painel[projeto.pk].vencendo) == (1, 1)
        assert painel[projeto.pk].status_prazo == StatusPrazo.ATRASADO
        assert (painel[projeto.pk].inicio, painel[projeto.pk].fim) == (date(2026, 9, 1), date(2026, 10, 1))
        assert (painel[vazio.pk].progresso, painel[vazio.pk].atrasadas, painel[vazio.pk].fim) == (0, 0, None)
        assert painel[vazio.pk].status_prazo == StatusPrazo.SEM_PRAZO
