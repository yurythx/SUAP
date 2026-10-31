"""Acesso à tela do projeto (`/projetos_ensino/projeto/<id>/`) e à sua impressão por quem não participa dele."""

import pytest
from django.contrib.auth.models import Group

from projetos_ensino.tests.conftest import _login
from rh.tests.factories import ServidorFactory

GRUPO_VISUALIZADOR_ENSINO = 'Visualizador de Projetos de Ensino'
GRUPO_VISUALIZADOR_EXTENSAO = 'Visualizador de Projetos'


def _rotas(projeto):
    return [f'/projetos_ensino/projeto/{projeto.pk}/', f'/projetos_ensino/imprimir_projeto/{projeto.pk}/?html=1']


@pytest.mark.django_db(databases='__all__')
def test_visualizador_de_projetos_de_ensino_ve_projeto_de_que_nao_participa(client, projeto):
    """Só com o grupo de Visualizador do Ensino (sem o grupo Servidor), abre e imprime projeto alheio (#17545)."""
    visualizador = ServidorFactory()
    _login(client, visualizador)
    # depois do login: o login devolve o grupo Servidor ao servidor
    visualizador.get_user().groups.set([Group.objects.get(name=GRUPO_VISUALIZADOR_ENSINO)])

    for rota in _rotas(projeto):
        assert client.get(rota).status_code == 200, rota


@pytest.mark.django_db(databases='__all__')
def test_visualizador_de_projetos_de_extensao_nao_ve_projeto_de_ensino(client, projeto):
    """O Visualizador de Projetos da Extensão, com o grupo Servidor, não abre nem imprime projeto de ensino alheio (#17545)."""
    servidor = ServidorFactory()
    _login(client, servidor)
    servidor.get_user().groups.add(Group.objects.get(name=GRUPO_VISUALIZADOR_EXTENSAO))
    assert servidor.get_user().has_perm('projetos_ensino.pode_visualizar_projeto')

    for rota in _rotas(projeto):
        assert client.get(rota).status_code == 403, rota
