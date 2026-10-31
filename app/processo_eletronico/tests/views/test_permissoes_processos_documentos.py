"""Permissões de processos/documentos: username inexistente responde 404 (era 500).

A view é acessível por superusuário com ``username`` na URL; o ``User.objects.get()`` sem
guarda estourava ``User.DoesNotExist`` (500) quando o username não existia.
"""

import pytest


@pytest.fixture
def cliente_admin(client, dois_servidores):
    """Superusuário com setor — sem setor com campus o middleware o deslogaria."""
    usuario = dois_servidores.a.get_user()
    usuario.is_superuser = True
    usuario.is_staff = True
    usuario.save()
    client.force_login(usuario)
    return client


def test_username_inexistente_responde_404(cliente_admin):
    """Username inexistente não derruba a view: o ``get_object_or_404`` responde 404."""
    resposta = cliente_admin.get('/processo_eletronico/permissoes_processos_documentos/nao-existe/')
    assert resposta.status_code == 404


def test_username_valido_responde_200(cliente_admin, dois_servidores):
    """Superusuário continua consultando as permissões de outro usuário normalmente."""
    alvo = dois_servidores.b.get_user().username
    resposta = cliente_admin.get(f'/processo_eletronico/permissoes_processos_documentos/{alvo}/')
    assert resposta.status_code == 200


def test_proprias_permissoes_responde_200(cliente_admin):
    """Sem username na URL, a view mostra as permissões do próprio usuário."""
    resposta = cliente_admin.get('/processo_eletronico/permissoes_processos_documentos/')
    assert resposta.status_code == 200
