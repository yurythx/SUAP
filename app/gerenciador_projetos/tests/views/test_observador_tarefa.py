"""Observar uma tarefa e deixar de observar, pelos botões do olho na página da tarefa."""

from __future__ import annotations

from django.contrib.auth.models import Group
from django.urls import reverse

from gerenciador_projetos.tests.factories import ProjetoFactory, TarefaFactory
from rh.tests.factories import ServidorFactory


class TestObservadorTarefa:
    def test_membro_observa_e_deixa_de_observar(self, client):
        membro = ServidorFactory().get_user()
        membro.groups.add(Group.objects.get(name='Membro de Projeto'))
        projeto = ProjetoFactory(criado_por=membro)
        projeto.membros.add(membro)
        tarefa = TarefaFactory(projeto=projeto, criado_por=membro)
        outro = ServidorFactory().get_user()
        tarefa.observadores.add(outro)
        client.force_login(membro)
        pagina = reverse('tarefa', args=[tarefa.pk])

        client.get(reverse('adicionar_observador', args=[tarefa.pk]))  # GET não altera nada
        assert not tarefa.observadores.filter(pk=membro.pk).exists()

        client.post(reverse('adicionar_observador', args=[tarefa.pk]))
        assert tarefa.observadores.filter(pk=membro.pk).exists()
        assert reverse('remover_observador', args=[tarefa.pk]) in client.get(pagina).content.decode()

        client.get(reverse('remover_observador', args=[tarefa.pk]))  # GET não altera nada
        assert tarefa.observadores.filter(pk=membro.pk).exists()

        client.post(reverse('remover_observador', args=[tarefa.pk]))
        assert set(tarefa.observadores.all()) == {outro}, 'deve sair só quem clicou'
        assert reverse('adicionar_observador', args=[tarefa.pk]) in client.get(pagina).content.decode()
