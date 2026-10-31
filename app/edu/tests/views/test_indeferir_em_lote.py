"""Indeferimento de requerimentos em lote com ``ids`` vazio ou com lixo (#17447).

Pedaço vazio ou não numérico em ``?ids=`` chegava ao ``filter(id__in=...)`` e estourava
``ValueError``; agora a leitura passa pelo ``djtools.utils.http.ids_da_query``.
"""

from __future__ import annotations

import pytest
from django.test import Client

from rh.tests.factories import ServidorFactory

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize('query', ['', '?ids=', '?ids=,,abc'])
def test_ids_invalidos_abrem_o_formulario_sem_erro(client: Client, sync_permissions, query: str) -> None:
    user = ServidorFactory().get_user()
    user.is_superuser = True
    user.save()
    client.force_login(user)

    resposta = client.get('/edu/indeferir_em_lote/' + query)

    assert resposta.status_code == 200
