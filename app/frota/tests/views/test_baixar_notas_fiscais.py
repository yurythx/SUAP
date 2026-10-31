"""Download das notas fiscais de manutenção em lote com ``ids`` ausente, vazio ou com lixo (#17447).

``GET.get('ids') and ...split(',')`` virava ``None`` sem o parâmetro (``filter(id__in=None)``) e
pedaço vazio ou não numérico estourava ``ValueError``; agora a leitura passa pelo
``djtools.utils.http.ids_da_query`` e a resposta é um zip vazio.
"""

from __future__ import annotations

import pytest
from django.test import Client

from rh.tests.factories import ServidorFactory

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize('query', ['', '?ids=', '?ids=,,abc'])
def test_ids_invalidos_devolvem_zip_vazio(client: Client, sync_permissions, query: str) -> None:
    user = ServidorFactory().get_user()
    user.is_superuser = True
    user.save()
    client.force_login(user)

    resposta = client.get('/frota/baixar_notas_fiscais_servicos/' + query)

    assert resposta.status_code == 200
    assert resposta['Content-Type'] == 'application/zip'
