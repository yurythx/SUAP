"""API REST do terminal de ponto (``/terminais/...``, ``terminais/views.py``).

São endpoints anônimos, autorizados só pelo IP de uma ``ponto.Maquina`` ativa com
``cliente_ponto`` (``terminais.utils.get_maquina``). O que se afirma aqui é a auditoria: todo
acesso autorizado deixa um ``MaquinaLog`` de qual máquina chamou o quê (#17450 — só
``frequencias`` deixava). O ``REMOTE_ADDR`` é explícito e fora do ``127.0.0.1``, que o e2e do
``comum`` cadastra como máquina ativa (ver ``comum/tests/views/test_webservice.py``).
"""

from __future__ import annotations

import base64

import pytest
from django.http import HttpResponse
from django.test import Client

from comum.models import Configuracao
from ponto.models import MaquinaLog
from ponto.tests.factories import MaquinaFactory
from rh.tests.factories import ServidorFactory

pytestmark = pytest.mark.django_db

IP_TERMINAL = '10.99.0.42'
IP_DESCONHECIDO = '10.99.0.201'


ROTAS = [
    # (método, rota, status esperado, operação registrada)
    ('get', '/terminais/funcionarios/', 200, 'terminais_funcionarios'),
    ('post', '/terminais/digitais/', 200, 'terminais_digitais'),
    ('get', '/terminais/frequencias/dia/{matricula}/', 200, 'terminais_frequencias_dia'),
    ('get', '/terminais/ocorrencias/{matricula}/', 400, 'terminais_ocorrencias'),
    ('get', '/terminais/solicitar_autocadastro/{matricula}/', 200, 'terminais_solicitar_autocadastro'),
    ('get', '/terminais/confirmar_autocadastro/{matricula}/', 200, 'terminais_confirmar_autocadastro'),
    ('get', '/terminais/cancelar_autocadastro/{matricula}/123456/', 200, 'terminais_cancelar_autocadastro'),
    ('get', '/terminais/whoami/', 200, 'terminais_whoami'),
]


def _chamar(client: Client, metodo: str, rota: str, matricula: str, ip: str) -> HttpResponse:
    """Chama a rota como o terminal chamaria; o ``POST`` de ``digitais`` leva uma digital válida."""
    dados = {'matricula': matricula, 'template': base64.b64encode(b'DIGITAL').decode()} if metodo == 'post' else None
    return getattr(client, metodo)(rota.format(matricula=matricula), data=dados, REMOTE_ADDR=ip)


@pytest.mark.parametrize(('metodo', 'rota', 'status', 'operacao'), ROTAS, ids=[rota[3] for rota in ROTAS])
def test_acesso_da_maquina_fica_registrado(client: Client, sync_permissions: None, metodo: str, rota: str, status: int, operacao: str) -> None:
    maquina = MaquinaFactory(ip=IP_TERMINAL, cliente_ponto=True)
    servidor = ServidorFactory()
    # ``ocorrencias`` lê a expiração do autocadastro; sem ela a view quebra em ``int(None)``.
    Configuracao.objects.update_or_create(app='comum', chave='biometria_expiracao', defaults={'valor': '7'})
    Configuracao.clear_cache()

    resposta = _chamar(client, metodo, rota, servidor.matricula, IP_TERMINAL)

    assert resposta.status_code == status
    assert MaquinaLog.objects.filter(maquina=maquina, operacao=operacao).count() == 1


@pytest.mark.parametrize(('metodo', 'rota', 'status', 'operacao'), ROTAS, ids=[rota[3] for rota in ROTAS])
def test_ip_desconhecido_e_recusado_sem_registro(client: Client, metodo: str, rota: str, status: int, operacao: str) -> None:
    maquina = MaquinaFactory(ip=IP_TERMINAL, cliente_ponto=True)

    resposta = _chamar(client, metodo, rota, 'qualquer', IP_DESCONHECIDO)

    assert resposta.status_code == 400
    assert not MaquinaLog.objects.filter(maquina=maquina).exists()
