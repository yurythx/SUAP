from types import SimpleNamespace

import pytest

from djtools.new_tests.utils import _should_ignore_console_error


def _msg(texto):
    return SimpleNamespace(text=texto, location={'url': 'http://localhost/comum/solicitar_trocar_senha/'})


@pytest.mark.parametrize(
    ('texto', 'ignorado'),
    [
        # Ruído do navegador: não é erro da aplicação e não pode derrubar cenário.
        ('requestStorageAccess: Permission denied.', True),
        ('[Violation] Permissions policy violation: compute-pressure is not allowed', True),
        ('Failed to load resource: the server responded with a status of 404 (Not Found)', True),
        # Erro real da aplicação: tem que continuar derrubando.
        ('Uncaught TypeError: undefined is not a function', False),
        ('Failed to load resource: net::ERR_CONNECTION_REFUSED', False),
    ],
)
def test_filtra_apenas_ruido_do_navegador(texto, ignorado):
    assert _should_ignore_console_error(_msg(texto)) is ignorado
