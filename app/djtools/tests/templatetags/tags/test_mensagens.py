"""Mensagens do esqueleto anunciadas a leitor de tela: erro interrompe, o resto é status."""

import pytest
from django.contrib import messages
from django.contrib.messages.storage.base import Message
from django.template.loader import render_to_string

TEMPLATE = 'components/messages.html'


@pytest.mark.parametrize(
    ('nivel', 'classe', 'role'),
    [
        (messages.ERROR, 'alert', 'alert'),
        (messages.SUCCESS, 'alert', 'status'),
        (messages.INFO, 'errornote', 'alert'),
    ],
)
def test_mensagem_anuncia_com_role_conforme_gravidade(nivel: int, classe: str, role: str) -> None:
    html = render_to_string(TEMPLATE, {'messages': [Message(nivel, 'Texto.')], 'classe': classe})
    assert f'role="{role}"' in html
