"""Rejeição de solicitação de assinatura (#17524).

O mesmo vínculo pode ter mais de uma solicitação pendente no documento; o ``get_object_or_404``
estourava ``MultipleObjectsReturned``. Agora rejeita a mais antiga, como a assinatura faz.
"""

from __future__ import annotations

import pytest
from django.test import Client

from documento_eletronico.models import CompartilhamentoDocumentoPessoa, NivelPermissao, SolicitacaoAssinatura
from documento_eletronico.status import DocumentoStatus, SolicitacaoStatus
from documento_eletronico.tests.factories import DocumentoTextoFactory, SolicitacaoAssinaturaFactory
from rh.tests.factories import ServidorFactory

pytestmark = pytest.mark.django_db


def test_rejeita_com_mais_de_uma_solicitacao_pendente(client: Client, sync_permissions) -> None:
    dono = ServidorFactory().get_user()
    signatario = ServidorFactory()
    documento = DocumentoTextoFactory(usuario_criacao=dono, status=DocumentoStatus.STATUS_AGUARDANDO_ASSINATURA)
    for _ in range(3):
        solicitacao = SolicitacaoAssinaturaFactory(documento=documento, solicitante=dono, solicitado=signatario.get_vinculo())
        CompartilhamentoDocumentoPessoa.objects.create(
            documento=documento,
            vinculo_permitido=signatario.get_vinculo(),
            nivel_permissao=NivelPermissao.LER,
            usuario_criacao=dono,
            solicitacao_assinatura=solicitacao,
        )
    client.force_login(signatario.get_user())

    resposta = client.post(
        f'/documento_eletronico/rejeitar_assinatura/{documento.pk}/',
        {'justificativa_rejeicao': 'Não concordo com o conteúdo.'},
    )

    assert resposta.status_code == 302
    rejeitadas = SolicitacaoAssinatura.objects.filter(documento=documento, status=SolicitacaoStatus.STATUS_INDEFERIDA)
    assert rejeitadas.count() == 1


def test_sem_solicitacao_pendente_retorna_404(client: Client, sync_permissions) -> None:
    dono = ServidorFactory().get_user()
    documento = DocumentoTextoFactory(usuario_criacao=dono)
    client.force_login(dono)

    resposta = client.get(f'/documento_eletronico/rejeitar_assinatura/{documento.pk}/')

    assert resposta.status_code == 404
