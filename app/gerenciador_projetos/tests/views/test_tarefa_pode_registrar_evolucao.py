"""Testa se a tela da tarefa esconde o registro de evolução quando a tarefa está
bloqueada para novas ações (Concluída, Cancelada, Suspensa ou de projeto encerrado)."""

from __future__ import annotations

import pytest
from django.urls import reverse

from gerenciador_projetos.enums import SituacaoTarefa
from gerenciador_projetos.models import Projeto, Tarefa
from rh.models import UnidadeOrganizacional


class TestPodeRegistrarEvolucao:
    def _tarefa(self, situacao: int) -> Tarefa:
        uo, _ = UnidadeOrganizacional.objects.get_or_create(setor=self.setor, defaults={'nome': 'Teste', 'sigla': 'TEST'})
        projeto = Projeto.objects.create(titulo='Projeto', descricao='desc', uo=uo, criado_por=self.user_admin)
        projeto.gerentes.add(self.user_admin)
        return Tarefa.objects.create(titulo='Tarefa', projeto=projeto, criado_por=self.user_admin, situacao=situacao)

    def test_nao_pode_registrar_evolucao_em_tarefa_cancelada_sem_data_conclusao(self, client):
        tarefa = self._tarefa(SituacaoTarefa.CANCELADA)
        assert tarefa.data_conclusao is None
        client.force_login(self.user_admin)

        response = client.get(reverse('tarefa', args=[tarefa.pk]))

        assert response.status_code == 200
        assert response.context['pode_registrar_evolucao'] is False

    def test_pode_registrar_evolucao_em_tarefa_aberta(self, client):
        tarefa = self._tarefa(SituacaoTarefa.ABERTA)
        client.force_login(self.user_admin)

        response = client.get(reverse('tarefa', args=[tarefa.pk]))

        assert response.status_code == 200
        assert response.context['pode_registrar_evolucao'] is True
