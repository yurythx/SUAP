"""Grupo Monitor de Projetos: lê os projetos públicos sem estar na equipe e sem editar; os privados seguem só para a equipe."""

from __future__ import annotations

from django.contrib.auth.models import Group
from django.urls import reverse

from comum.models import User
from gerenciador_projetos.enums import VisibilidadeProjeto
from gerenciador_projetos.tests.factories import ProjetoFactory, TarefaFactory
from rh.tests.factories import ServidorFactory

LISTAGEM = '/admin/gerenciador_projetos/projeto/?tab=tab_any_data'


def _usuario_no_grupo(nome_grupo: str) -> User:
    usuario = ServidorFactory().get_user()
    usuario.groups.add(Group.objects.get(name=nome_grupo))
    return usuario


class TestMonitorProjetos:
    def test_monitor_fora_da_equipe_ve_o_projeto_publico_sem_editar(self, client):
        projeto = ProjetoFactory(criado_por=self.user_admin, visibilidade=VisibilidadeProjeto.PUBLICO)
        tarefa = TarefaFactory(projeto=projeto, criado_por=self.user_admin)
        client.force_login(_usuario_no_grupo('Monitor de Projetos'))

        listagem = client.get(LISTAGEM)
        pagina = client.get(reverse('projeto', args=[projeto.pk]))
        assert client.get(reverse('tarefa', args=[tarefa.pk])).status_code == 200
        edicao = client.get(f'/admin/gerenciador_projetos/projeto/{projeto.pk}/change/')

        assert projeto in listagem.context['cl'].result_list
        assert pagina.status_code == 200
        assert not any(
            pagina.context[flag] for flag in ('pode_editar_projeto', 'pode_editar_tarefas', 'pode_adicionar_tarefas', 'pode_registrar_evolucao')
        )
        assert edicao.status_code == 403

    def test_monitor_nao_ve_projeto_privado_alheio(self, client):
        privado = ProjetoFactory(criado_por=self.user_admin)
        tarefa = TarefaFactory(projeto=privado, criado_por=self.user_admin)
        client.force_login(_usuario_no_grupo('Monitor de Projetos'))

        listagem = client.get(LISTAGEM)

        assert privado not in listagem.context['cl'].result_list
        assert client.get(reverse('tarefa', args=[tarefa.pk])).status_code == 403
        for rota in ('projeto', 'dashboard', 'gantt'):
            assert client.get(reverse(rota, args=[privado.pk])).status_code == 403, rota
        assert privado.titulo not in client.get(f'{reverse("comparar_projetos")}?projeto={privado.pk}').content.decode()

    def test_monitor_continua_vendo_o_privado_da_propria_equipe(self, client):
        monitor = _usuario_no_grupo('Monitor de Projetos')
        privado = ProjetoFactory(criado_por=self.user_admin)
        privado.membros.add(monitor)
        client.force_login(monitor)

        assert privado in client.get(LISTAGEM).context['cl'].result_list
        assert client.get(reverse('projeto', args=[privado.pk])).status_code == 200

    def test_usuario_fora_do_grupo_e_da_equipe_continua_barrado(self, client):
        publico = ProjetoFactory(criado_por=self.user_admin, visibilidade=VisibilidadeProjeto.PUBLICO)
        client.force_login(_usuario_no_grupo('Interessado do Projeto'))

        listagem = client.get(LISTAGEM)
        pagina = client.get(reverse('projeto', args=[publico.pk]))

        assert publico not in listagem.context['cl'].result_list
        assert pagina.status_code == 403

    def test_fora_da_equipe_nao_abre_dashboard_gantt_nem_tarefa(self, client):
        projeto = ProjetoFactory(criado_por=self.user_admin)
        tarefa = TarefaFactory(projeto=projeto, criado_por=self.user_admin)
        client.force_login(_usuario_no_grupo('Interessado do Projeto'))

        assert client.get(reverse('dashboard', args=[projeto.pk])).status_code == 403
        assert client.get(reverse('gantt', args=[projeto.pk])).status_code == 403
        assert client.get(reverse('tarefa', args=[tarefa.pk])).status_code == 403
