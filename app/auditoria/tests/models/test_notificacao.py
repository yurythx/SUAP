"""Notificações da auditoria: texto livre digitado pelo usuário chega escapado no HTML."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from auditoria.notificacao import Notificar
from auditoria.tests.factories import AcaoFactory, PaintFactory


def test_solicitacao_de_ciencia_escapa_texto_livre_no_corpo() -> None:
    """Motivo, assunto e nome da ação vão para o corpo HTML como texto, não como marcação.

    Nenhum model atual tem ``motivo``/``comunicacao`` nem ``Acao.paint``: o método espera a
    forma legada, então a ciência e a comunicação são montadas à mão em volta da ação real.
    """
    acao = AcaoFactory.build(nome='<b>Ação</b>')
    acao.paint = PaintFactory.build()
    ciencia = SimpleNamespace(
        comunicacao=SimpleNamespace(acao=acao, objetivo='<b>Assunto</b>'),
        motivo='<b>Motivo</b>',
        solicitante='Solicitante',
        data_solicitacao=datetime(2026, 10, 13, 9, 0),
        prazo_atual=lambda: datetime(2026, 10, 20, 9, 0),
    )

    with patch('auditoria.notificacao.send_notification') as send_notification:
        Notificar.enviar_notificacao_ciencia(ciencia, destinatarios=[])

    corpo = send_notification.call_args.args[1]
    assert '&lt;b&gt;Motivo&lt;/b&gt;' in corpo
    assert '&lt;b&gt;Assunto&lt;/b&gt;' in corpo
    assert '&lt;b&gt;Ação&lt;/b&gt;' in corpo
    assert '<b>' not in corpo
