"""Tela de solicitar assinatura: o formulário de preenchimento em lote só valida quando submetido."""

from __future__ import annotations

import pytest
from django.test import Client

from documento_eletronico.status import DocumentoStatus
from documento_eletronico.tests.factories import DocumentoTextoFactory
from rh.tests.factories import ServidorFactory

pytestmark = pytest.mark.django_db


def test_lote_so_valida_quando_submetido(client: Client, sync_permissions) -> None:
    dono = ServidorFactory().get_user()
    documento = DocumentoTextoFactory(usuario_criacao=dono, status=DocumentoStatus.STATUS_CONCLUIDO)
    client.force_login(dono)
    url = f'/documento_eletronico/solicitar_assinatura/{documento.pk}/'

    abertura = client.get(url)
    submissao_vazia = client.get(url, {'solicitados': ''})

    assert abertura.status_code == 200
    assert 'Por favor, corrija os erros abaixo.' not in abertura.content.decode()
    assert 'Por favor, corrija os erros abaixo.' in submissao_vazia.content.decode()
