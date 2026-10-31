import pytest
from django.test import Client

from documento_eletronico.models import Documento, DocumentoTexto
from documento_eletronico.status import DocumentoStatus
from documento_eletronico.tests.factories import DocumentoTextoFactory
from rh.tests.factories import ServidorFactory


@pytest.mark.django_db
def test_nao_favorita_documento_que_nao_pode_ler(client: Client, sync_permissions: None) -> None:
    autor = ServidorFactory()
    documento = DocumentoTextoFactory(
        usuario_criacao=autor.get_user(),
        setor_dono=autor.setor,
        status=DocumentoStatus.STATUS_FINALIZADO,
        nivel_acesso=Documento.NIVEL_ACESSO_RESTRITO,
    )
    outro = ServidorFactory().get_user()
    assert not documento.pode_ler(outro)
    client.force_login(outro)

    resposta = client.get(f'/documento_eletronico/gerenciar_favoritos/{documento.pk}/add/')

    assert resposta.status_code == 403
    assert not DocumentoTexto.objects.filter(pk=documento.pk, usuarios_marcadores_favoritos=outro).exists()
