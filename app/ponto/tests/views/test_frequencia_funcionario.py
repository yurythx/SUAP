"""Frequências de um servidor consultadas por outro (``/ponto/ajax/get_frequencia_funcionario/``).

Quem tem ``pode_ver_frequencia_campus`` (p.ex. o Coordenador de Gestão de Pessoas) só vê as
frequências de servidor do próprio campus. A regra comparava ``servidor.setor.uo`` com a ``uo``
do setor do usuário logado e estourava ``AttributeError`` (500) quando o servidor consultado
estava sem setor (#17855): sem setor não há campus para conferir, e o escopo do campus nega.
"""

from __future__ import annotations

import datetime

import pytest
from django.contrib.auth.models import Group
from django.test import Client

from comum.models import User
from rh.models import Servidor
from rh.tests.factories import ServidorFactory

pytestmark = pytest.mark.django_db

DIA = datetime.date(2026, 10, 1)


def _coordenador_gestao_pessoas(**kwargs: object) -> User:
    user = ServidorFactory(**kwargs).get_user()
    user.groups.add(Group.objects.get(name='Coordenador de Gestão de Pessoas'))
    return user


def _consultar(client: Client, servidor: Servidor) -> int:
    periodo = {'matricula': servidor.matricula, 'data_inicio': f'{DIA:%d/%m/%Y}', 'data_fim': f'{DIA:%d/%m/%Y}'}
    return client.get('/ponto/ajax/get_frequencia_funcionario/', periodo).status_code


def test_coordenador_nao_ve_frequencias_de_servidor_sem_setor(client: Client, sync_permissions: None) -> None:
    servidor = ServidorFactory(setor=None)
    client.force_login(_coordenador_gestao_pessoas())

    assert _consultar(client, servidor) == 403


def test_coordenador_ve_frequencias_de_servidor_do_mesmo_campus(client: Client, sync_permissions: None) -> None:
    coordenador = _coordenador_gestao_pessoas()
    servidor = ServidorFactory(setor=coordenador.get_relacionamento().setor)
    client.force_login(coordenador)

    assert _consultar(client, servidor) == 200
