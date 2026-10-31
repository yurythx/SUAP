"""Registrar evolução: slider de 0 a 100% com o valor ao lado, e a tarefa com avanço parcial passa a Em andamento."""

from __future__ import annotations

from django.urls import reverse

from gerenciador_projetos.enums import SituacaoTarefa
from gerenciador_projetos.models import Tarefa
from gerenciador_projetos.tests.factories import ProjetoFactory, TarefaFactory
from rh.tests.factories import ServidorFactory


class TestPercentualNoRegistrarEvolucao:
    def test_registrar_evolucao_usa_slider_com_o_percentual_atual(self, client):
        gerente = ServidorFactory().get_user()
        projeto = ProjetoFactory(criado_por=gerente)
        projeto.gerentes.add(gerente)
        tarefa = TarefaFactory(projeto=projeto, criado_por=gerente, percentual_executado=40)
        client.force_login(gerente)

        html = client.get(reverse('gerenciar_historicoevolucao', args=[tarefa.pk])).content.decode()

        assert 'type="range"' in html
        assert 'value="40"' in html
        assert '40%</output>' in html

    def test_evolucao_parcial_poe_a_tarefa_em_andamento_qualquer_que_seja_a_situacao(self, client):
        gerente = ServidorFactory().get_user()
        projeto = ProjetoFactory(criado_por=gerente)
        projeto.gerentes.add(gerente)
        aberta, sem_avanco, em_analise = (
            TarefaFactory(projeto=projeto, criado_por=gerente),
            TarefaFactory(projeto=projeto, criado_por=gerente),
            TarefaFactory(projeto=projeto, criado_por=gerente, situacao=SituacaoTarefa.EM_ANALISE),
        )
        client.force_login(gerente)

        for tarefa, percentual in ((aberta, 30), (sem_avanco, 0), (em_analise, 30)):
            client.post(reverse('gerenciar_historicoevolucao', args=[tarefa.pk]), {'comentario': 'avanço', 'percentual_executado': percentual})

        situacoes = {t.pk: Tarefa.objects.get(pk=t.pk).situacao for t in (aberta, sem_avanco, em_analise)}
        assert situacoes == {
            aberta.pk: SituacaoTarefa.EM_ANDAMENTO,
            sem_avanco.pk: SituacaoTarefa.ABERTA,
            em_analise.pk: SituacaoTarefa.EM_ANDAMENTO,
        }
