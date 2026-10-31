"""Validação/invalidação de documentação em lote com ``ids`` ausente, vazio ou com lixo (#17447).

``GET.get('ids') and ...split(',')`` virava ``None`` sem o parâmetro (``TypeError`` no ``for``) e
pedaço vazio ou não numérico estourava ``ValueError`` no ``get_object_or_404``; agora a leitura
passa pelo ``djtools.utils.http.ids_da_query``.
"""

from __future__ import annotations

import datetime

import pytest
from django.test import Client

from ae.tests.factories import InscricaoFactory
from edu.models import Aluno
from rh.tests.factories import ServidorFactory

pytestmark = pytest.mark.django_db

VALIDAR = '/ae/informar_data_entrega_documentacao/'
INVALIDAR = '/ae/informar_ausencia_documentacao/'


@pytest.fixture
def cliente(client: Client, sync_permissions) -> Client:
    user = ServidorFactory().get_user()
    user.is_superuser = True
    user.save()
    client.force_login(user)
    return client


def _validar(cliente: Client, query: str):
    return cliente.post(VALIDAR + query, {'data': datetime.date.today().strftime('%d/%m/%Y'), 'url': '/ae/'})


@pytest.mark.parametrize('query', ['', '?ids=', '?ids=,,abc'])
def test_validar_com_ids_invalidos_nao_documenta_ninguem(cliente: Client, query: str) -> None:
    inscricao = InscricaoFactory()

    resposta = _validar(cliente, query)

    assert resposta.status_code == 302
    assert not Aluno.objects.get(pk=inscricao.aluno_id).documentada


def test_validar_pk_valido_ao_lado_de_lixo_continua_documentando(cliente: Client) -> None:
    inscricao = InscricaoFactory()

    resposta = _validar(cliente, f'?ids={inscricao.pk},,abc')

    assert resposta.status_code == 302
    assert Aluno.objects.get(pk=inscricao.aluno_id).documentada


@pytest.mark.parametrize('query', ['', '?ids=', '?ids=,,abc'])
def test_invalidar_com_ids_invalidos_nao_mexe_em_ninguem(cliente: Client, query: str) -> None:
    inscricao = InscricaoFactory()

    resposta = cliente.get(INVALIDAR + query)

    assert resposta.status_code == 302
    assert not Aluno.objects.get(pk=inscricao.aluno_id).documentacao_invalidada


def test_invalidar_pk_valido_ao_lado_de_lixo_continua_invalidando(cliente: Client) -> None:
    inscricao = InscricaoFactory()

    resposta = cliente.get(f'{INVALIDAR}?ids={inscricao.pk},,abc')

    assert resposta.status_code == 302
    assert Aluno.objects.get(pk=inscricao.aluno_id).documentacao_invalidada
