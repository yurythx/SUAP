"""E-mail de senha exposta enviado ao usuário quando a senha é expirada em lote."""

import datetime
from types import SimpleNamespace

import pytest

from comum.models import Configuracao
from ldap_backend import tasks


def _email_de_senha_exposta(monkeypatch: pytest.MonkeyPatch) -> str:
    # Fronteiras externas: notificação e e-mail.
    enviados = []
    monkeypatch.setattr(tasks, 'send_notification', lambda *args, **kwargs: None)
    monkeypatch.setattr(tasks, 'send_mail', lambda titulo, mensagem, de, para: enviados.append(mensagem))
    Configuracao.clear_cache()
    contexto = {
        'url_redefinir_senha': 'http://suap/comum/solicitar_trocar_senha/',
        'url_senhas_expostas': 'http://suap/admin/comum/senhaexposta/',
        'categoria': 'Alerta de senha exposta',
        'expire_date': datetime.datetime.now(),
    }
    user = SimpleNamespace(username='1234567')

    tasks.notificar_senha_exposta(user, None, 'Fulano', 'fulano@gmail.com', True, [], contexto)

    assert len(enviados) == 1, 'o e-mail de senha exposta deveria ter sido enviado'
    return enviados[0]


@pytest.mark.django_db
def test_sem_sigla_da_instituicao_email_usa_texto_neutro(monkeypatch) -> None:
    Configuracao.objects.filter(app='comum', chave='instituicao_sigla').delete()

    mensagem = _email_de_senha_exposta(monkeypatch)

    assert 'Ação Necessária para sua Conta</h1>' in mensagem
    assert 'acesso as máquinas institucionais.' in mensagem
    assert 'None' not in mensagem
    assert 'junto ao' not in mensagem


@pytest.mark.django_db
def test_com_sigla_da_instituicao_email_cita_a_sigla(monkeypatch) -> None:
    Configuracao.objects.update_or_create(app='comum', chave='instituicao_sigla', defaults={'valor': 'IFXX'})

    mensagem = _email_de_senha_exposta(monkeypatch)

    assert 'Ação Necessária para sua Conta junto ao IFXX</h1>' in mensagem
    assert 'acesso as máquinas institucionais do IFXX.' in mensagem
