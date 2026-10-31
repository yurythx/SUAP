"""As ações do projeto permanecem disponíveis nas seis telas de visualização."""

from __future__ import annotations

from django.contrib.auth.models import Group
from django.urls import reverse

from gerenciador_projetos.tests.factories import ProjetoFactory
from rh.tests.factories import ServidorFactory


def test_gerente_ve_acao_editar_em_todas_as_visualizacoes(client) -> None:
    gerente = ServidorFactory().get_user()
    gerente.groups.add(Group.objects.get(name='Gerente de Projeto'))
    projeto = ProjetoFactory(criado_por=gerente)
    projeto.gerentes.add(gerente)
    client.force_login(gerente)
    url_edicao = f'/admin/gerenciador_projetos/projeto/{projeto.pk}/'
    visualizacoes = (
        'projeto',
        'dashboard',
        'gantt',
        'calendario',
        'status_projeto',
        'evolucao_tarefas_projeto',
    )

    for nome in visualizacoes:
        resposta = client.get(reverse(nome, args=[projeto.pk]))

        assert resposta.status_code == 200, nome
        assert f'href="{url_edicao}"' in resposta.content.decode(), nome
