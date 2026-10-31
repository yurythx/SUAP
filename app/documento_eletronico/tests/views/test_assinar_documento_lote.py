"""Assinatura de documentos em lote: ``ids`` ausente, vazio ou com lixo (#17447) e acesso anônimo (#17460).

``self.request.GET['ids'].split('-')`` estourava ``MultiValueDictKeyError`` sem o parâmetro e
``ValueError`` com pedaço vazio ou não numérico no ``filter(id__in=...)``; agora a leitura passa
pelo ``djtools.utils.http.ids_da_query`` (separador ``-``, o que o admin monta).
"""

from __future__ import annotations

import pytest
from django.conf import settings
from django.shortcuts import resolve_url
from django.test import Client

from documento_eletronico.models import AssinaturaDocumentoTexto, RegistroAcaoDocumento, RegistroAcaoDocumentoTexto
from documento_eletronico.tests.factories import DocumentoTextoFactory
from rh.tests.factories import PapelFactory, ServidorFactory

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize('query', ['', '?ids=', '?ids=-,-abc', '?ids=999999-abc'])
def test_ids_invalidos_nao_assinam_nada(client: Client, sync_permissions, query: str) -> None:
    servidor = ServidorFactory()
    papel = PapelFactory(servidor=servidor)
    user = servidor.get_user()
    user.set_password('123')
    user.save()
    client.force_login(user)

    resposta = client.post('/documento_eletronico/assinar_documento_lote/' + query, {'senha': '123', 'papel': papel.pk})

    assert resposta.status_code == 302
    assert not RegistroAcaoDocumentoTexto.objects.exists()


def test_anonimo_redirecionado_para_login_sem_assinar(client: Client, sync_permissions) -> None:
    """Anônimo, mesmo com a senha certa de um servidor, vai para o login e nada é assinado (#17460)."""
    servidor = ServidorFactory()
    papel = PapelFactory(servidor=servidor)
    user = servidor.get_user()
    user.set_password('123')
    user.save()
    documento = DocumentoTextoFactory(usuario_criacao=user)
    url = f'/documento_eletronico/assinar_documento_lote/?ids={documento.pk}'

    respostas = [
        client.get(url),
        client.post(url, {'senha': '123', 'papel': papel.pk}),
    ]

    for resposta in respostas:
        assert resposta.status_code == 302
        assert resposta['Location'].startswith(resolve_url(settings.LOGIN_URL))
    assert not AssinaturaDocumentoTexto.objects.filter(documento=documento).exists()
    assert not RegistroAcaoDocumentoTexto.objects.filter(tipo=RegistroAcaoDocumento.TIPO_ASSINATURA).exists()


def test_servidor_autenticado_acessa_assinatura_em_lote(client: Client, sync_permissions) -> None:
    servidor = ServidorFactory()
    PapelFactory(servidor=servidor)
    client.force_login(servidor.get_user())

    resposta = client.get('/documento_eletronico/assinar_documento_lote/?ids=1')

    assert resposta.status_code == 200


@pytest.mark.parametrize(
    'url',
    [
        '/documento_eletronico/assinar_documento_com_token/1/',
        '/documento_eletronico/assinar_documento_token/1/',
        '/documento_eletronico/validar_assinatura_token/1/',
    ],
)
def test_assinatura_por_token_removida(client: Client, sync_permissions: None, url: str) -> None:
    """A assinatura por token nunca foi usada e não verificava a cadeia ICP-Brasil: as rotas saíram (#17470, #17471)."""
    client.force_login(ServidorFactory().get_user())

    assert client.post(url, {'cert': 'x', 'sig': 'y', 'data': 'z', 'role': '1'}).status_code == 404
