"""Acesso às telas internas de assinatura digital (``/comum/assinar_documento/`` e ``/comum/verificar_documento/``).

O ``comum/menu.yaml`` só mostra as duas entradas a Reitor e Diretor Geral, e as views passaram a
exigir os mesmos grupos (#17400): antes bastava estar logado para abri-las digitando a URL.
A validação pública (``/comum/validar_assinatura/``) segue anônima e não é tratada aqui.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Group
from django.test import Client

from rh.tests.factories import ServidorFactory

pytestmark = pytest.mark.django_db

ROTAS = ['/comum/assinar_documento/', '/comum/verificar_documento/']


def _logar_servidor(client: Client, grupo: str | None = None) -> Client:
    user = ServidorFactory().get_user()
    if grupo:
        user.groups.add(Group.objects.get(name=grupo))
    client.force_login(user)
    return client


@pytest.mark.parametrize('rota', ROTAS)
def test_servidor_sem_grupo_de_dirigente_recebe_403(client: Client, sync_permissions, rota: str) -> None:
    assert _logar_servidor(client).get(rota).status_code == 403


@pytest.mark.parametrize('grupo', ['Reitor', 'Diretor Geral'])
@pytest.mark.parametrize('rota', ROTAS)
def test_dirigente_abre_a_tela(client: Client, sync_permissions, rota: str, grupo: str) -> None:
    assert _logar_servidor(client, grupo).get(rota).status_code == 200
