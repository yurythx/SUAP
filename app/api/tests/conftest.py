"""Fixtures compartilhadas dos testes da API (formato pytest funcional).

Os testes de integração pedem o substrato mínimo (``servidor_a``, ``campus_a``...),
construído pelas factories do ``rh``, e ``api_client``, que expõe o client SUAP com a
autenticação da API mockada. Os dados-folha de cada domínio ficam em fixtures locais do
próprio módulo de teste.

Endpoints *passthrough* (que só repassam o retorno de um método de modelo) são testados
sem banco: mockam o método e usam ``api_client`` com um usuário falso — ver
``api_client_db_free``.
"""

from unittest import mock

import pytest

from pgd2.tests.conftest import cadeia_rit_pgd2
from pgd2.tests.models.test_workflow_pgd2 import workflow_pgd2
from rh.tests.factories import ServidorFactory


@pytest.fixture
def api_client(suap_client, api_auth_mocks):
    """Client SUAP com ``SessionAuth``/``TrustedAppAuth`` mockados.

    A autenticação lê ``request.META['user']`` — injetado via ``client.get(url, user=...)``.
    """
    return suap_client


@pytest.fixture
def servidor_a(db, sync_permissions):
    """Servidor do substrato. O ``SetorFactory`` dá ao setor um campus próprio."""
    return ServidorFactory()


@pytest.fixture
def servidor_b(db, sync_permissions):
    """Segundo servidor, no campus dele: usado onde o teste precisa de dois atores."""
    return ServidorFactory()


@pytest.fixture
def campus_a(servidor_a):
    return servidor_a.setor.uo


@pytest.fixture
def campus_b(servidor_b):
    """Campus do segundo servidor.

    Vem do servidor, não de um `SetorFactory` solto, porque o endpoint de estatísticas
    agrupa por campus a partir de quem está lotado nele: campus vazio não aparece.
    """
    return servidor_b.setor.uo


@pytest.fixture
def fake_user():
    """Usuário falso para testes sem banco (passthrough).

    Passa por ``authenticate_side_effect`` (basta ``is_authenticated``); o método de
    modelo que tocaria o banco é mockado pelo teste, então nenhuma query é necessária.
    """
    user = mock.Mock()
    user.is_authenticated = True
    return user
