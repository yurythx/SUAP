"""Testa a reordenação dos itens do checklist de uma Tarefa (drag-and-drop)."""

from __future__ import annotations

import pytest
from django.test import Client
from django.urls import reverse

from gerenciador_projetos.enums import SituacaoTarefa
from gerenciador_projetos.models import ItemChecklist, Projeto, Tarefa
from rh.models import UnidadeOrganizacional


class TestReordenarChecklist:
    def _tarefa_com_itens(self) -> tuple[Tarefa, list[ItemChecklist]]:
        uo, _ = UnidadeOrganizacional.objects.get_or_create(setor=self.setor, defaults={'nome': 'Teste', 'sigla': 'TEST'})
        projeto = Projeto.objects.create(titulo='Projeto', descricao='desc', uo=uo, criado_por=self.user_admin)
        projeto.gerentes.add(self.user_admin)
        tarefa = Tarefa.objects.create(titulo='Tarefa', projeto=projeto, criado_por=self.user_admin)
        itens = [ItemChecklist.objects.create(tarefa=tarefa, descricao=f'Item {i}', posicao=i) for i in range(3)]
        return tarefa, itens

    def test_novo_item_recebe_proxima_posicao(self, client):
        tarefa, _itens = self._tarefa_com_itens()
        client.force_login(self.user_admin)

        client.post(reverse('gerenciar_checklist', args=[tarefa.pk]), {'descricao': 'Item 3', 'action': 'add'})

        novo_item = ItemChecklist.objects.get(descricao='Item 3')
        assert novo_item.posicao == 3

    def test_reordena_itens(self, client):
        tarefa, itens = self._tarefa_com_itens()
        client.force_login(self.user_admin)
        nova_ordem = [itens[2].id, itens[0].id, itens[1].id]

        response = client.post(reverse('gerenciar_checklist', args=[tarefa.pk]), {'action': 'reordenar', 'ordem[]': nova_ordem})

        assert response.status_code == 200
        posicoes = {item.id: ItemChecklist.objects.get(pk=item.id).posicao for item in itens}
        assert posicoes[itens[2].id] == 0
        assert posicoes[itens[0].id] == 1
        assert posicoes[itens[1].id] == 2

    def test_recusa_alteracao_sem_token_csrf(self) -> None:
        tarefa, itens = self._tarefa_com_itens()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user_admin)

        response = client.post(reverse('gerenciar_checklist', args=[tarefa.pk]), {'item_id': itens[0].pk, 'action': 'toggle'})

        assert response.status_code == 403
        itens[0].refresh_from_db()
        assert itens[0].concluido is False

    def test_tela_configura_csrf_nas_requisicoes_ajax(self, client: Client) -> None:
        tarefa, _itens = self._tarefa_com_itens()
        client.force_login(self.user_admin)

        response = client.get(reverse('tarefa', args=[tarefa.pk]))

        conteudo = response.content.decode()
        assert 'name="csrfmiddlewaretoken"' in conteudo
        assert "'X-CSRFToken': csrfToken" in conteudo

    def test_adiciona_item_com_token_csrf_da_tela(self) -> None:
        tarefa, _itens = self._tarefa_com_itens()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user_admin)
        client.get(reverse('tarefa', args=[tarefa.pk]))
        csrf_token = client.cookies['csrftoken'].value

        response = client.post(
            reverse('gerenciar_checklist', args=[tarefa.pk]),
            {'descricao': 'Item criado com CSRF', 'action': 'add'},
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        assert response.status_code == 200
        assert ItemChecklist.objects.filter(tarefa=tarefa, descricao='Item criado com CSRF').exists()

    def test_listagem_via_get_respeita_posicao(self, client):
        tarefa, itens = self._tarefa_com_itens()
        itens[0].posicao, itens[2].posicao = itens[2].posicao, itens[0].posicao
        itens[0].save()
        itens[2].save()
        client.force_login(self.user_admin)

        response = client.get(reverse('gerenciar_checklist', args=[tarefa.pk]))

        descricoes = [item['descricao'] for item in response.json()['itens']]
        assert descricoes == ['Item 2', 'Item 1', 'Item 0']

    @pytest.mark.parametrize('situacao', [SituacaoTarefa.CONCLUIDA, SituacaoTarefa.CANCELADA])
    def test_tela_nao_exibe_acoes_de_checklist_em_tarefa_bloqueada(self, client, situacao):
        tarefa, _itens = self._tarefa_com_itens()
        tarefa.situacao = situacao
        tarefa.save()
        client.force_login(self.user_admin)

        response = client.get(reverse('tarefa', args=[tarefa.pk]))

        assert response.status_code == 200
        conteudo = response.content.decode()
        assert 'id="adicionarNovoItem"' not in conteudo
        assert 'deletarItem' not in conteudo
        assert 'onclick="toggleItem' not in conteudo
        assert '$("#checklist").sortable' not in conteudo
        assert '<input type="checkbox" disabled' in conteudo

    @pytest.mark.parametrize('situacao', [SituacaoTarefa.CONCLUIDA, SituacaoTarefa.CANCELADA])
    @pytest.mark.parametrize(
        ('action', 'dados_extra'),
        [
            ('add', {'descricao': 'Item novo'}),
            ('toggle', {}),
            ('delete', {}),
            ('reordenar', {}),
        ],
    )
    def test_bloqueia_alteracoes_em_tarefa_concluida_ou_cancelada(self, client, situacao, action, dados_extra):
        tarefa, itens = self._tarefa_com_itens()
        tarefa.situacao = situacao
        tarefa.save()
        client.force_login(self.user_admin)
        dados = {'action': action, **dados_extra}
        if action in ('toggle', 'delete'):
            dados['item_id'] = itens[0].id
        elif action == 'reordenar':
            dados['ordem[]'] = [item.id for item in itens]

        response = client.post(reverse('gerenciar_checklist', args=[tarefa.pk]), dados)

        assert response.status_code == 302
        assert not ItemChecklist.objects.filter(descricao='Item novo').exists()
        assert ItemChecklist.objects.get(pk=itens[0].id).concluido is False
