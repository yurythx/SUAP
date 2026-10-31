"""Testa a alteração rápida do percentual executado da Tarefa entre as opções
fixas 0/25/50/75/100%."""

from __future__ import annotations

import datetime

import pytest
from django.test import Client
from django.urls import reverse

from gerenciador_projetos.enums import SituacaoTarefa
from gerenciador_projetos.models import Projeto, Tarefa
from rh.models import UnidadeOrganizacional


class TestAlterarProgressoTarefa:
    def _tarefa(self) -> Tarefa:
        uo, _ = UnidadeOrganizacional.objects.get_or_create(setor=self.setor, defaults={'nome': 'Teste', 'sigla': 'TEST'})
        projeto = Projeto.objects.create(titulo='Projeto', descricao='desc', uo=uo, criado_por=self.user_admin)
        projeto.gerentes.add(self.user_admin)
        return Tarefa.objects.create(titulo='Tarefa', projeto=projeto, criado_por=self.user_admin)

    @pytest.mark.parametrize('percentual', [0, 25, 50, 75, 100])
    def test_altera_progresso_para_opcoes_validas(self, client: Client, percentual: int) -> None:
        tarefa = self._tarefa()
        client.force_login(self.user_admin)

        response = client.post(reverse('alterar_progresso_tarefa', args=[tarefa.pk, percentual]), follow=True)

        assert response.status_code == 200
        tarefa.refresh_from_db()
        assert tarefa.percentual_executado == percentual
        if 0 < percentual < 100:
            assert tarefa.situacao == SituacaoTarefa.EM_ANDAMENTO
        elif percentual == 100:
            assert tarefa.situacao == SituacaoTarefa.CONCLUIDA
            assert tarefa.data_conclusao == datetime.date.today()
        else:
            assert tarefa.situacao == SituacaoTarefa.ABERTA

    def test_recusa_percentual_fora_das_opcoes(self, client):
        tarefa = self._tarefa()
        client.force_login(self.user_admin)

        response = client.post(reverse('alterar_progresso_tarefa', args=[tarefa.pk, 42]))

        assert response.status_code == 404

    def test_get_nao_altera_progresso(self, client):
        """GET não deve mudar estado: alterar_progresso_tarefa é uma mudança de
        estado e deve exigir POST real, assim como alterar_situacao_tarefa."""
        tarefa = self._tarefa()
        percentual_original = tarefa.percentual_executado
        client.force_login(self.user_admin)

        client.get(reverse('alterar_progresso_tarefa', args=[tarefa.pk, 75]))

        tarefa.refresh_from_db()
        assert tarefa.percentual_executado == percentual_original

    def test_recusa_post_sem_token_csrf(self, client: Client) -> None:
        tarefa = self._tarefa()
        client.force_login(self.user_admin)
        client.handler.enforce_csrf_checks = True

        response = client.post(reverse('alterar_progresso_tarefa', args=[tarefa.pk, 75]))

        assert response.status_code == 403
        tarefa.refresh_from_db()
        assert tarefa.percentual_executado != 75

    def test_altera_progresso_para_100_gera_exatamente_um_historico(self, client):
        """A conclusão via `alterar_progresso` passa por `fechar_tarefa()`, que não deve
        criar histórico manualmente — apenas o automático de `save()` via `has_changed`."""
        tarefa = self._tarefa()
        qtd_historico_antes = tarefa.get_historicoevolucao().count()
        client.force_login(self.user_admin)

        client.post(reverse('alterar_progresso_tarefa', args=[tarefa.pk, 100]), follow=True)

        assert tarefa.get_historicoevolucao().count() == qtd_historico_antes + 1
