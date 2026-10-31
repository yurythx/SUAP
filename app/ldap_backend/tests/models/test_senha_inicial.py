"""Senha inicial da conta criada no AD."""

import datetime
from types import SimpleNamespace

import pytest

from comum.models import Configuracao
from ldap_backend.utils import get_senha_inicial

PESSOA = SimpleNamespace(nascimento_data=datetime.date(2000, 1, 31))


@pytest.fixture(autouse=True)
def sem_senha_randomica_forcada() -> None:
    Configuracao.objects.filter(app='ldap_backend', chave='utilizar_senha_randomica').delete()


@pytest.mark.django_db
def test_com_sigla_senha_inicial_e_sigla_e_nascimento() -> None:
    Configuracao.objects.update_or_create(app='comum', chave='instituicao_sigla', defaults={'valor': 'ifxx'})
    Configuracao.clear_cache()

    assert get_senha_inicial(PESSOA) == '@IFXX31012000'


@pytest.mark.django_db
def test_sem_sigla_senha_inicial_e_aleatoria() -> None:
    Configuracao.objects.filter(app='comum', chave='instituicao_sigla').delete()
    Configuracao.clear_cache()

    senha = get_senha_inicial(PESSOA)

    assert len(senha) == 12
    assert '31012000' not in senha
    assert 'NONE' not in senha
