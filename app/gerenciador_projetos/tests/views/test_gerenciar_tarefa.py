"""Testa o aviso exibido ao usuário quando uma tarefa é adicionada a um projeto
ainda em situação Aberto."""

from __future__ import annotations

import datetime

import pytest
from django.test import Client
from django.urls import reverse

from gerenciador_projetos.enums import PrioridadeTarefa, SituacaoProjeto, SituacaoTarefa
from gerenciador_projetos.models import Lista, ListaProjeto, Projeto, Tarefa, TipoAtividade
from rh.models import UnidadeOrganizacional


def _payload_nova_tarefa() -> dict:
    tipo_atividade = TipoAtividade.objects.create(nome='Tipo Teste')
    return {
        'titulo': 'Nova tarefa',
        'descricao': 'desc',
        'situacao': SituacaoTarefa.ABERTA,
        'tipo_atividade': tipo_atividade.pk,
        'prioridade': PrioridadeTarefa.MEDIA,
    }


class TestAvisoProjetoAberto:
    def _projeto(self, situacao: int) -> Projeto:
        uo, _ = UnidadeOrganizacional.objects.get_or_create(setor=self.setor, defaults={'nome': 'Teste', 'sigla': 'TEST'})
        projeto = Projeto.objects.create(titulo='Projeto Teste', descricao='desc', uo=uo, criado_por=self.user_admin, situacao=situacao)
        projeto.gerentes.add(self.user_admin)
        return projeto

    def test_avisa_quando_projeto_aberto_recebe_nova_tarefa(self, client):
        projeto = self._projeto(SituacaoProjeto.ABERTO)
        client.force_login(self.user_admin)

        response = client.post(reverse('adicionar_tarefa', args=[projeto.pk]), _payload_nova_tarefa(), follow=True)

        mensagens = [str(m) for m in response.context['messages']]
        assert any('ainda está com situação Aberto' in m for m in mensagens)

    def test_nao_avisa_quando_projeto_em_andamento_recebe_nova_tarefa(self, client):
        projeto = self._projeto(SituacaoProjeto.EM_ANDAMENTO)
        client.force_login(self.user_admin)

        response = client.post(reverse('adicionar_tarefa', args=[projeto.pk]), _payload_nova_tarefa(), follow=True)

        mensagens = [str(m) for m in response.context['messages']]
        assert not any('ainda está com situação Aberto' in m for m in mensagens)


class TestBloqueiaCadastroTarefaEmProjetoFinalizado:
    def _projeto(self, situacao: int) -> Projeto:
        uo, _ = UnidadeOrganizacional.objects.get_or_create(setor=self.setor, defaults={'nome': 'Teste', 'sigla': 'TEST'})
        projeto = Projeto.objects.create(titulo='Projeto Teste', descricao='desc', uo=uo, criado_por=self.user_admin, situacao=situacao)
        projeto.gerentes.add(self.user_admin)
        return projeto

    @pytest.mark.parametrize('situacao', [SituacaoProjeto.CONCLUIDO, SituacaoProjeto.CANCELADO])
    def test_bloqueia_cadastro_de_tarefa(self, client, situacao):
        projeto = self._projeto(situacao)
        client.force_login(self.user_admin)
        # Visita a página do projeto antes para popular o breadcrumb de sessão (`bc`);
        # sem isso o redirect de erro ('..') cai no próprio request.path e gera loop.
        client.get(reverse('projeto', args=[projeto.pk]))

        response = client.post(reverse('adicionar_tarefa', args=[projeto.pk]), {'titulo': 'Nova tarefa'}, follow=True)

        assert not projeto.tarefa_set.filter(titulo='Nova tarefa').exists()
        mensagens = [str(m) for m in response.context['messages']]
        assert any('não tem permissão para adicionar' in m for m in mensagens)


class TestCampoListaAoEditarTarefa:
    def _projeto_com_lista(self) -> tuple[Projeto, Lista]:
        from gerenciador_projetos.models import ListaProjeto

        uo, _ = UnidadeOrganizacional.objects.get_or_create(setor=self.setor, defaults={'nome': 'Teste', 'sigla': 'TEST'})
        projeto = Projeto.objects.create(titulo='Projeto com lista', descricao='desc', uo=uo, criado_por=self.user_admin)
        projeto.gerentes.add(self.user_admin)
        lista = Lista.objects.create(nome='A Fazer', criada_por=self.user_admin)
        ListaProjeto.objects.create(lista=lista, projeto=projeto, posicao=1)
        return projeto, lista

    def test_campo_lista_aparece_quando_projeto_tem_listas(self, client):
        from gerenciador_projetos.forms import TarefaFormFactory

        projeto, _ = self._projeto_com_lista()
        client.force_login(self.user_admin)
        FormClass = TarefaFormFactory(request=None, projeto=projeto)
        form = FormClass()
        assert 'lista' in form.fields

    def test_campo_lista_nao_aparece_quando_projeto_sem_listas(self, client):
        from gerenciador_projetos.forms import TarefaFormFactory

        uo, _ = UnidadeOrganizacional.objects.get_or_create(setor=self.setor, defaults={'nome': 'Teste', 'sigla': 'TEST'})
        projeto = Projeto.objects.create(titulo='Projeto sem lista', descricao='desc', uo=uo, criado_por=self.user_admin)
        FormClass = TarefaFormFactory(request=None, projeto=projeto)
        form = FormClass()
        assert 'lista' not in form.fields

    def test_selecionar_lista_no_form_sincroniza_dashboard(self, client):
        projeto, lista = self._projeto_com_lista()
        client.force_login(self.user_admin)

        payload = _payload_nova_tarefa()
        payload['lista'] = lista.pk
        response = client.post(reverse('adicionar_tarefa', args=[projeto.pk]), payload, follow=True)

        assert response.status_code == 200
        tarefa = Tarefa.objects.get(titulo='Nova tarefa')
        assert tarefa.lista_id == lista.pk
        assert list(lista.get_tarefas(projeto)) == [tarefa]

    def test_lista_selecionada_na_edicao_prevalece_sobre_parametro_da_url(self, client) -> None:
        projeto, lista_anterior = self._projeto_com_lista()
        lista_nova = Lista.objects.create(nome='Em andamento', criada_por=self.user_admin)
        ListaProjeto.objects.create(lista=lista_nova, projeto=projeto, posicao=2)
        payload = _payload_nova_tarefa()
        tarefa = Tarefa.objects.create(
            titulo='Tarefa existente',
            descricao='desc',
            projeto=projeto,
            criado_por=self.user_admin,
            tipo_atividade_id=payload['tipo_atividade'],
        )
        tarefa.mover_para_lista(lista_anterior, self.user_admin)
        client.force_login(self.user_admin)
        payload['lista'] = lista_nova.pk

        response = client.post(f'{reverse("alterar_tarefa", args=[projeto.pk, tarefa.pk])}?lista={lista_anterior.pk}', payload, follow=True)

        assert response.status_code == 200
        tarefa.refresh_from_db()
        assert tarefa.lista_id == lista_nova.pk
        assert tarefa.get_listaatual().lista_id == lista_nova.pk

    def test_data_de_conclusao_na_edicao_conclui_tarefa(self, client: Client) -> None:
        projeto, _ = self._projeto_com_lista()
        payload = _payload_nova_tarefa()
        tarefa = Tarefa.objects.create(
            titulo='Tarefa existente',
            descricao='desc',
            projeto=projeto,
            criado_por=self.user_admin,
            tipo_atividade_id=payload['tipo_atividade'],
        )
        payload['data_conclusao'] = datetime.date.today().strftime('%d/%m/%Y')
        client.force_login(self.user_admin)

        response = client.post(reverse('alterar_tarefa', args=[projeto.pk, tarefa.pk]), payload, follow=True)

        assert response.status_code == 200
        tarefa.refresh_from_db()
        assert tarefa.data_conclusao == datetime.date.today()
        assert tarefa.percentual_executado == 100
        assert tarefa.situacao == SituacaoTarefa.CONCLUIDA
