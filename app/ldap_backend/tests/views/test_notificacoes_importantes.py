"""Aviso de desativação do vínculo exibido no início do SUAP."""

import datetime
from types import SimpleNamespace

import pytest

from comum.models import Configuracao
from ldap_backend.views import index_notificacoes_importantes


def _avisos() -> list[str]:
    Configuracao.clear_cache()
    expira = datetime.datetime.today() + datetime.timedelta(days=30)
    request = SimpleNamespace(
        user=SimpleNamespace(username='1234567', is_authenticated=True),
        session={'adAccountExpires_1234567': expira.isoformat()},
    )
    return index_notificacoes_importantes(sender=None, request=request)


@pytest.mark.django_db
def test_sem_sigla_da_instituicao_aviso_usa_texto_neutro() -> None:
    Configuracao.objects.filter(app='comum', chave='instituicao_sigla').delete()

    [aviso] = _avisos()

    assert 'Seu vínculo - 1234567 - com a instituição será desativado' in aviso
    assert 'demais sistemas da instituição com sua senha' in aviso
    assert 'None' not in aviso
    assert 'IFRN' not in aviso


@pytest.mark.django_db
def test_com_sigla_da_instituicao_aviso_cita_a_sigla_configurada() -> None:
    Configuracao.objects.update_or_create(app='comum', chave='instituicao_sigla', defaults={'valor': 'IFXX'})

    [aviso] = _avisos()

    assert 'Seu vínculo - 1234567 - com o IFXX será desativado' in aviso
    assert 'demais sistemas do IFXX com sua senha' in aviso
    assert 'IFRN' not in aviso
