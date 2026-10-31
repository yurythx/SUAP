"""Tela de edição das tags de anonimização (``editar_tags_anonimizacao``), restrita a superusuário."""

from unittest.mock import patch

import pytest
from django.test import Client

from comum.models import Configuracao, User
from documento_eletronico.models import DocumentoTexto
from documento_eletronico.status import DocumentoStatus
from documento_eletronico.tests.factories import DocumentoTextoFactory
from rh.tests.factories import ServidorFactory

CORPO_COM_SCRIPT = '<p>Ofício</p><img src="x" onerror="alert(`xss-no-corpo`)">'


def _documento_finalizado(usuario: User) -> DocumentoTexto:
    servidor = usuario.get_vinculo().relacionamento
    return DocumentoTextoFactory(
        usuario_criacao=usuario,
        setor_dono=servidor.setor,
        status=DocumentoStatus.STATUS_FINALIZADO,
        corpo=CORPO_COM_SCRIPT,
        identificador_tipo_documento_sigla='OF',
        identificador_numero=1,
        identificador_ano=2026,
        identificador_setor_sigla=servidor.setor.sigla,
        tags_anonimizacao=['Tag manual'],
    )


@pytest.mark.django_db
def test_reprocessamento_exige_a_permissao_da_tela(client: Client, sync_permissions: None) -> None:
    documento = _documento_finalizado(ServidorFactory().get_user())
    leitor = ServidorFactory().get_user()
    assert documento.pode_ler(leitor)
    Configuracao.objects.create(app='comum', chave='suap_ai_url', valor='http://suap-ai.invalido')
    client.force_login(leitor)

    with patch('documento_eletronico.models.requests.post') as post:
        post.return_value.status_code = 200
        post.return_value.json.return_value = [{'text': 'Tag do SUAP-AI'}]
        resposta = client.get(f'/documento_eletronico/editar_tags_anonimizacao/{documento.pk}/?auto_reprocessar=1')

    assert resposta.status_code == 403
    assert not post.called
    assert DocumentoTexto.objects.get(pk=documento.pk).tags_anonimizacao == ['Tag manual']


@pytest.mark.django_db
def test_corpo_exibido_ao_superusuario_sai_sanitizado(client: Client, sync_permissions: None) -> None:
    superusuario = ServidorFactory().get_user()
    User.objects.filter(pk=superusuario.pk).update(is_superuser=True)
    superusuario.refresh_from_db()
    documento = _documento_finalizado(superusuario)
    client.force_login(superusuario)

    resposta = client.get(f'/documento_eletronico/editar_tags_anonimizacao/{documento.pk}/')

    assert resposta.status_code == 200
    html = resposta.content.decode()
    assert '<p>Ofício</p>' in html
    assert 'xss-no-corpo' not in html
