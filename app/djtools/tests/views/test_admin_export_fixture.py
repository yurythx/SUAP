"""Exportação da listagem do admin para fixture (``?export_to_fixture=1``) (#17717).

O ``dumpdata`` devolve a tabela inteira, ignorando o ``get_queryset`` do admin e as permissões: só o
superusuário exporta, e só nos admins que declaram ``export_to_fixture`` — a mesma regra do botão.
Para os demais o parâmetro é ignorado e a listagem segue normal.
"""

from __future__ import annotations

import json

import pytest
from django.test import Client

from comum.models import User
from documento_eletronico.tests.factories import DocumentoTextoFactory
from edu.tests.factories import AlunoFactory
from rh.tests.factories import ServidorFactory

pytestmark = pytest.mark.django_db

DOCUMENTOS = '/admin/documento_eletronico/documentotexto/'  # admin sem ``export_to_fixture``
NATUREZAS = '/admin/edu/naturezaparticipacao/'  # admin com ``export_to_fixture``
EXPORTAR = {'export_to_fixture': '1'}


def _superusuario() -> User:
    user = ServidorFactory().get_user()
    user.is_superuser = True
    user.save()
    return user


def test_usuario_comum_nao_exporta_a_tabela(client: Client, sync_permissions: None) -> None:
    DocumentoTextoFactory(usuario_criacao=ServidorFactory().get_user())
    client.force_login(AlunoFactory().get_user())

    resposta = client.get(DOCUMENTOS, EXPORTAR)

    assert resposta.status_code == 200
    assert not resposta.has_header('Content-Disposition')
    assert 'cl' in resposta.context
    assert 'Exportar para Fixture' not in resposta.content.decode()


def test_superusuario_exporta_onde_o_admin_declara(client: Client, sync_permissions: None) -> None:
    client.force_login(_superusuario())

    assert 'Exportar para Fixture' in client.get(NATUREZAS).content.decode()
    resposta = client.get(NATUREZAS, EXPORTAR)

    assert resposta.status_code == 200
    assert resposta['Content-Disposition'] == 'attachment; filename=edu.naturezaparticipacao.json'
    assert isinstance(json.loads(resposta.content), list)


def test_superusuario_nao_exporta_onde_o_admin_nao_declara(client: Client, sync_permissions: None) -> None:
    client.force_login(_superusuario())

    resposta = client.get(DOCUMENTOS, EXPORTAR)

    assert resposta.status_code == 200
    assert not resposta.has_header('Content-Disposition')
    assert 'cl' in resposta.context
