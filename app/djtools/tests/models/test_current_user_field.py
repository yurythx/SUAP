"""Regressão: CurrentUserField não pode resolver o default para AnonymousUser.

Em requisição anônima (ou por vazamento de threadlocal entre testes sob xdist),
``tl.get_user()`` devolve um ``AnonymousUser``. Como o default do campo é
``tl.get_user``, esse objeto acabava em ``<campo>_id`` e quebrava o INSERT com
``TypeError: Field 'id' expected a number``. O default deve tratá-lo como ausência
de usuário (None).
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import AnonymousUser

from djtools.db.models.fields.foreignkey import CurrentUserField
from djtools.middleware import threadlocals as tl
from djtools.models import TwoFactorAuthenticationCode


@pytest.fixture(autouse=True)
def _limpa_threadlocal():
    yield
    tl.context.__dict__.pop('user', None)


def _campo() -> CurrentUserField:
    campo = TwoFactorAuthenticationCode._meta.get_field('user')
    assert isinstance(campo, CurrentUserField)
    return campo


def test_get_default_none_quando_sem_usuario():
    tl.context.__dict__.pop('user', None)
    assert _campo().get_default() is None


def test_get_default_ignora_anonymous():
    tl.context.user = AnonymousUser()
    assert _campo().get_default() is None


def test_get_default_converte_usuario_autenticado_em_pk():
    from comum.models import User

    user = User(username='fulano')
    user.pk = 42
    tl.context.user = user
    assert _campo().get_default() == 42
