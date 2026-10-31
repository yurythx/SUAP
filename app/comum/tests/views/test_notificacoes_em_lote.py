"""Ações em lote da caixa de notificações com ``ids`` ausente, vazio ou com lixo na query string.

Mesma raiz de #17406: ``request.GET.get('ids').split(',')`` estourava ``AttributeError`` sem o
parâmetro e ``ValueError`` com pedaço vazio. A leitura passa pelo ``djtools.utils.http.ids_da_query``.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from django.conf import settings
from django.test import Client

from comum.models import RegistroNotificacao
from djtools.utils import send_notification
from rh.tests.factories import ServidorFactory

pytestmark = pytest.mark.django_db

ROTAS = ['/comum/marcar_como_lida_em_lote/', '/comum/marcar_como_nao_lida_em_lote/', '/comum/remover_notificacoes_em_lote/']


@pytest.fixture
def cliente_com_uma_notificacao(client: Client, sync_permissions) -> tuple[Client, RegistroNotificacao]:
    user = ServidorFactory().get_user()
    vinculo = user.get_vinculo()
    client.force_login(user)
    send_notification('Lote', 'Notificação do lote.', settings.DEFAULT_FROM_EMAIL, [vinculo], categoria='Lote', so_notificar=True)
    return client, RegistroNotificacao.objects.get(vinculo=vinculo)


@pytest.mark.parametrize('rota', ROTAS)
@pytest.mark.parametrize('query', ['', '?ids=', '?ids=,,abc'])
def test_ids_invalidos_redirecionam_sem_alterar_nada(cliente_com_uma_notificacao: tuple[Client, RegistroNotificacao], rota: str, query: str) -> None:
    client, registro = cliente_com_uma_notificacao

    resposta = client.get(rota + query)

    assert resposta.status_code == 302
    assert RegistroNotificacao.objects.filter(pk=registro.pk, lida=False).exists()


def test_pk_valido_ao_lado_de_lixo_continua_marcando(cliente_com_uma_notificacao: tuple[Client, RegistroNotificacao]) -> None:
    client, registro = cliente_com_uma_notificacao

    resposta = client.get(f'/comum/marcar_como_lida_em_lote/?ids={registro.pk},,abc')

    assert resposta.status_code == 302
    registro.refresh_from_db()
    assert registro.lida


def test_lote_marca_as_legiveis_e_pula_a_travada(cliente_com_uma_notificacao: tuple[Client, RegistroNotificacao]) -> None:
    """A travada no meio do lote fica não lida e não impede as demais (#17388)."""
    client, legivel = cliente_com_uma_notificacao
    send_notification(
        'Travada',
        'Notificação com bloqueio de leitura.',
        settings.DEFAULT_FROM_EMAIL,
        [legivel.vinculo],
        categoria='Travada',
        so_notificar=True,
        data_permite_marcar_lida=datetime.now() + timedelta(days=3),
    )
    travada = RegistroNotificacao.objects.exclude(pk=legivel.pk).get(vinculo=legivel.vinculo)
    assert not travada.pode_ler(), 'pré-condição: a notificação deveria estar travada'

    client.get(f'/comum/marcar_como_lida_em_lote/?ids={travada.pk},{legivel.pk}')

    assert RegistroNotificacao.objects.get(pk=legivel.pk).lida, 'a travada no lote impediu a leitura da legível'
    assert not RegistroNotificacao.objects.get(pk=travada.pk).lida, 'o lote marcou como lida uma notificação travada'
