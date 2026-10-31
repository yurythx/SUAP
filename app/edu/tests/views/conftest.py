"""Fixtures compartilhadas dos testes DB-free de views do edu.

``make_request`` monta um request via ``RequestFactory`` com ``user``/``session``/``_messages``
prontos para chamar o corpo cru de uma view (`inspect.unwrap`) sem tocar o banco.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def make_request(rf):
    """Factory de request: ``make_request(method='post', path='/?x=1', user=...)``."""

    def _build(method='get', path='/', user=None, **kwargs):
        request = getattr(rf, method)(path, **kwargs)
        request.user = user or MagicMock(is_authenticated=True)
        request.session = {}
        request._messages = MagicMock()
        from comum.utils import tl

        tl.context.request = request
        tl.context.user = request.user
        return request

    return _build
