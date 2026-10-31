"""Detalhe de máquina de ponto (``/comum/maquinas/detalhes/<pk>/``): situação "ligada" via ``ping``.

A view pinga o IP do terminal. A fronteira mockada é ``subprocess.run`` (processo externo); o que
se verifica é o que a tela mostra e que o comando vai como lista de argumentos, sem shell.
"""

from __future__ import annotations

import subprocess
from unittest import mock

import pytest

from comum.tests.factories import UserFactory
from ponto.tests.factories import MaquinaFactory

pytestmark = pytest.mark.django_db

URL = '/comum/maquinas/detalhes/{pk}/'


def _abrir_detalhe(client, **run_kwargs: object) -> tuple[object, mock.MagicMock, object]:
    maquina = MaquinaFactory()
    client.force_login(UserFactory(is_superuser=True))
    with mock.patch('subprocess.run', **run_kwargs) as run:
        resposta = client.get(URL.format(pk=maquina.pk))
    assert resposta.status_code == 200
    return resposta, run, maquina


def test_maquina_que_responde_ao_ping_aparece_ligada(client):
    resposta, run, maquina = _abrir_detalhe(client, return_value=subprocess.CompletedProcess([], 0))

    assert resposta.context['maquina_ligada'] is True
    comando = run.call_args.args[0]
    assert isinstance(comando, list), 'o ping voltou a ser montado como string de shell'
    assert comando[0] == 'ping'
    assert comando[-1] == maquina.ip
    assert run.call_args.kwargs.get('shell', False) is False
    assert run.call_args.kwargs.get('timeout'), 'sem timeout, um IP mudo segura o worker'


@pytest.mark.parametrize(
    'run_kwargs',
    [
        {'return_value': subprocess.CompletedProcess([], 1)},
        {'side_effect': subprocess.TimeoutExpired('ping', 2)},
        {'side_effect': FileNotFoundError('ping')},
    ],
    ids=['sem-resposta', 'timeout', 'ping-ausente'],
)
def test_maquina_que_nao_responde_aparece_desligada(client, run_kwargs):
    resposta, _run, _maquina = _abrir_detalhe(client, **run_kwargs)

    assert resposta.context['maquina_ligada'] is False
