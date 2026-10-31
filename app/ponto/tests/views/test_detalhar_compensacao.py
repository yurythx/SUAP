"""Detalhamento da compensação de horário de um dia (``/ponto/detalhar_compensacao/``).

O Coordenador de Gestão de Pessoas só vê o detalhamento de servidor do próprio campus. A
regra comparava ``servidor.setor.uo`` com a ``uo`` do setor do usuário logado e estourava
``AttributeError`` (500) quando o servidor consultado estava sem setor ou o usuário não tinha
relacionamento (#17855, Sentry SUAP-WY1). Sem setor não há campus para conferir: o critério do
campus nega, e os demais critérios (ver todos, o próprio servidor, a chefia) seguem valendo.

O coordenador sem setor não chega à view: o ``UsuarioSemSetorMiddleware`` desloga servidor sem
setor SUAP antes dela.
"""

from __future__ import annotations

import datetime

import pytest
from django.contrib.auth.models import Group
from django.test import Client

from comum.models import User
from comum.tests.factories import UserFactory
from rh.models import Servidor
from rh.tests.factories import ServidorFactory

pytestmark = pytest.mark.django_db

DIA = datetime.date(2026, 10, 1)


def _coordenador_gestao_pessoas(**kwargs: object) -> User:
    user = ServidorFactory(**kwargs).get_user()
    user.groups.add(Group.objects.get(name='Coordenador de Gestão de Pessoas'))
    return user


def _url(servidor: Servidor) -> str:
    return f'/ponto/detalhar_compensacao/{servidor.matricula}/{DIA:%d%m%Y}/'


def test_coordenador_nao_ve_servidor_sem_setor(client: Client, sync_permissions: None) -> None:
    servidor = ServidorFactory(setor=None)
    client.force_login(_coordenador_gestao_pessoas())

    resposta = client.get(_url(servidor))

    assert resposta.status_code == 403


def test_coordenador_ve_servidor_do_mesmo_campus(client: Client, sync_permissions: None) -> None:
    coordenador = _coordenador_gestao_pessoas()
    servidor = ServidorFactory(setor=coordenador.get_relacionamento().setor)
    client.force_login(coordenador)

    resposta = client.get(_url(servidor))

    assert resposta.status_code == 200


def test_superusuario_sem_vinculo_ve_compensacao(client: Client, sync_permissions: None) -> None:
    servidor = ServidorFactory()
    client.force_login(UserFactory(is_superuser=True, is_staff=True))

    resposta = client.get(_url(servidor))

    assert resposta.status_code == 200
