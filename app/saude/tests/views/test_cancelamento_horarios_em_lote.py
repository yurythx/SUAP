"""Justificativa de cancelamento de horários em lote com ``ids`` ausente, vazio ou com lixo (#17447).

``request.GET.get('ids').split(',')`` estourava ``AttributeError`` sem o parâmetro e ``ValueError``
com pedaço vazio; agora a leitura passa pelo ``djtools.utils.http.ids_da_query``.
"""

from __future__ import annotations

import pytest
from django.test import Client

from rh.tests.factories import ServidorFactory
from saude.models import HorarioAtendimento
from saude.tests.factories import HorarioAtendimentoFactory

pytestmark = pytest.mark.django_db

ROTA = '/saude/informar_motivo_cancelamento_horario/'


@pytest.fixture
def cliente(client: Client, sync_permissions) -> Client:
    user = ServidorFactory().get_user()
    user.is_superuser = True
    user.save()
    client.force_login(user)
    return client


@pytest.mark.parametrize('query', ['', '?ids=', '?ids=,,abc'])
def test_ids_invalidos_nao_cancelam_nada(cliente: Client, query: str) -> None:
    horario = HorarioAtendimentoFactory()

    resposta = cliente.post(ROTA + query, {'motivo_cancelamento': 'Motivo'})

    assert resposta.status_code == 302
    assert HorarioAtendimento.objects.filter(pk=horario.pk, cancelado=False).exists()


def test_pk_valido_ao_lado_de_lixo_continua_cancelando(cliente: Client) -> None:
    horario = HorarioAtendimentoFactory()

    resposta = cliente.post(f'{ROTA}?ids={horario.pk},,abc', {'motivo_cancelamento': 'Motivo'})

    assert resposta.status_code == 302
    horario.refresh_from_db()
    assert horario.cancelado
    assert horario.motivo_cancelamento == 'Motivo'
