"""Substrato dos testes do módulo de chaves.

Do antigo `suap_data` o módulo usava três coisas: um servidor com senha, o client e o
campus onde o prédio é cadastrado.
"""

import pytest

from rh.tests.factories import ServidorFactory

SENHA = '123'


@pytest.fixture
def operador(db, sync_permissions):
    """Servidor que opera as chaves. A senha não vem do `ServidorFactory`."""
    servidor = ServidorFactory()
    user = servidor.get_user()
    user.set_password(SENHA)
    user.save()
    return servidor
