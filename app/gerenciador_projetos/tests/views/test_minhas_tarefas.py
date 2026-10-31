"""Filtro por projeto da tela *Minhas Tarefas* (``views.minhas_tarefas``).

O quadro "Concluída" já ficou sempre vazio ao aplicar o filtro: a linha do filtro partia de
``tarefas_andamento`` (que carrega ``data_conclusao__isnull=True``) em vez de
``tarefas_concluidas``. As três tarefas do cenário cobrem os dois erros possíveis — a
concluída do projeto filtrado tem que aparecer (o bug antigo) e a de outro projeto não pode
(apagar o filtro "conserta" o primeiro assert e quebra este).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.urls import reverse

from gerenciador_projetos.enums import SituacaoTarefa
from gerenciador_projetos.models import Projeto, Tarefa
from rh.models import UnidadeOrganizacional


class TestFiltroMinhasTarefas:
    def _projeto(self, titulo: str) -> Projeto:
        uo, _ = UnidadeOrganizacional.objects.get_or_create(setor=self.setor, defaults={'nome': 'Teste', 'sigla': 'TEST'})
        return Projeto.objects.create(titulo=titulo, descricao=titulo, uo=uo, criado_por=self.user_admin)

    def _tarefa(self, projeto: Projeto, titulo: str, situacao: int) -> Tarefa:
        tarefa = Tarefa.objects.create(titulo=titulo, projeto=projeto, criado_por=self.user_admin, situacao=situacao)
        tarefa.atribuido_a.add(self.user_admin)
        return tarefa

    def test_filtro_por_projeto_preserva_as_concluidas(self, client):
        projeto_a = self._projeto('Projeto A')
        projeto_b = self._projeto('Projeto B')
        concluida_a = self._tarefa(projeto_a, 'Concluída A', SituacaoTarefa.CONCLUIDA)
        andamento_a = self._tarefa(projeto_a, 'Em andamento A', SituacaoTarefa.ABERTA)
        concluida_b = self._tarefa(projeto_b, 'Concluída B', SituacaoTarefa.CONCLUIDA)

        client.force_login(self.user_admin)
        response = client.post(reverse('minhas_tarefas'), {'projeto': projeto_a.pk})

        assert response.status_code == 200
        assert list(response.context['tarefas_concluidas']) == [concluida_a]
        assert list(response.context['tarefas_andamento']) == [andamento_a]
        assert concluida_b not in response.context['tarefas_concluidas']

    def test_card_destaca_data_estimada_ultrapassada(self, client):
        projeto = self._projeto('Projeto com atraso')
        data_atrasada = date.today() - timedelta(days=1)
        tarefa = self._tarefa(projeto, 'Tarefa atrasada', SituacaoTarefa.ABERTA)
        tarefa.data_conclusao_estimada = data_atrasada
        tarefa.save()

        client.force_login(self.user_admin)
        response = client.get(reverse('minhas_tarefas'))

        assert response.status_code == 200
        conteudo = response.content.decode()
        assert 'class="badge false"' in conteudo
        assert data_atrasada.strftime('%d/%m/%Y') in conteudo
