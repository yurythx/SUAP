"""Listagem de servidores a progredir no admin."""

from datetime import date, timedelta

import pytest
from django.contrib.auth.models import Group
from django.test import Client

from djtools.utils import get_datetime_now
from progressoes.tests.factories import ServidorAProgredirFactory
from rh.tests.factories import ServidorFactory

pytestmark = pytest.mark.django_db


def _hoje() -> date:
    return get_datetime_now().date()


def test_filtro_por_dias_desconta_o_saldo(client: Client, sync_permissions: None) -> None:
    coordenador = ServidorFactory()
    coordenador.get_user().groups.add(Group.objects.get(name='Coordenador de Gestão de Pessoas Sistêmico'))
    client.force_login(coordenador.get_user())
    com_saldo = ServidorAProgredirFactory(data_fim_contagem=_hoje() + timedelta(days=50), saldo_dias=30)
    sem_saldo = ServidorAProgredirFactory(data_fim_contagem=_hoje() + timedelta(days=50))

    response = client.get('/admin/progressoes/servidoraprogredir/', {'dias_filter': '30'})

    assert response.status_code == 200
    assert com_saldo.avaliado.matricula in response.content.decode()
    assert sem_saldo.avaliado.matricula not in response.content.decode()
