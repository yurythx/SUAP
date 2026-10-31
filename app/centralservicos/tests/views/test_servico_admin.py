"""Gestor só altera serviço da área que gere (#12567).

O admin lista os serviços pelos grupos de serviço do gestor, e um grupo pode ter categorias de
várias áreas: o gestor de uma área abria e alterava serviços de outra.
"""

from __future__ import annotations

import pytest
from django.test import Client

from centralservicos.tests.factories import CategoriaServicoFactory, GestorAreaServicoFactory, GrupoServicoFactory, ServicoFactory
from rh.tests.factories import ServidorFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def gestor_manutencao(sync_permissions) -> GestorAreaServicoFactory:
    return GestorAreaServicoFactory(gestor=ServidorFactory().get_user(), area__nome='Manutenção Predial')


def test_gestor_nao_altera_servico_de_outra_area(client: Client, gestor_manutencao) -> None:
    grupo_compartilhado = GrupoServicoFactory(categorias=[CategoriaServicoFactory(area=gestor_manutencao.area), CategoriaServicoFactory()])
    servico_de_outra_area = ServicoFactory(area__nome='Comunicação', grupo_servico=grupo_compartilhado)
    client.force_login(gestor_manutencao.gestor)

    resposta = client.post(f'/admin/centralservicos/servico/{servico_de_outra_area.pk}/change/', {'nome': 'Alterado'})

    assert resposta.status_code == 403


def test_gestor_abre_servico_da_sua_area(client: Client, gestor_manutencao) -> None:
    grupo = GrupoServicoFactory(categorias=[CategoriaServicoFactory(area=gestor_manutencao.area)])
    servico = ServicoFactory(area=gestor_manutencao.area, grupo_servico=grupo)
    client.force_login(gestor_manutencao.gestor)

    resposta = client.get(f'/admin/centralservicos/servico/{servico.pk}/change/')

    assert resposta.status_code == 200
