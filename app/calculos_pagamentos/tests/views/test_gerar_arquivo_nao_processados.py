"""Geração do arquivo batch com ``ids`` ausente, vazio ou com lixo (#17447).

A view guarda ``?ids=`` na sessão e o relê no envio do formulário. Estourava ``KeyError`` sem
``ids`` na sessão, ``KeyError`` no ``HTTP_REFERER`` com ``ids=`` e ``ValueError``/``DoesNotExist``
no ``Pagamento.objects.get`` com lixo ou pk inexistente; agora a leitura passa pelo
``djtools.utils.http.ids_da_query``.
"""

from __future__ import annotations

import pytest
from django.test import Client

from calculos_pagamentos.models.pagamentos import ArquivoPagamento
from rh.tests.factories import ServidorFactory

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ('query', 'status'),
    [('', 302), ('?ids=', 302), ('?ids=abc', 302), ('?ids=,,abc', 302), ('?ids=999999', 404), ('?ids=999999,,abc&mes=1&ano=2026', 404)],
)
def test_ids_invalidos_nao_geram_arquivo(client: Client, sync_permissions, query: str, status: int) -> None:
    user = ServidorFactory().get_user()
    user.is_superuser = True
    user.save()
    client.force_login(user)

    resposta = client.get('/calculos_pagamentos/gerar_arquivo_nao_processados/' + query)

    assert resposta.status_code == status
    assert not ArquivoPagamento.objects.exists()
