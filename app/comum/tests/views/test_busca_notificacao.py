"""Rolagem infinita da caixa de notificações: ``/comum/busca_notificacao/<ultimo_pk>/`` é rota de API.

O ``$.ajax`` de ``notificacoes.html`` pede ``dataType: "json"``, então TODA resposta tem de ser
JSON — inclusive o fim da lista. Antes do #17389 o fim devolvia ``None``, o ``@rtr()``
renderizava o ``default.html`` (200 ``text/html``) e o jQuery tratava o fim da caixa como erro
de rede.

A rolagem pagina por CURSOR (#17451): o parâmetro é o pk do último item exibido, e a view
devolve a não lida seguinte a ele na ordem da caixa. Por posição, a lista encolhia durante a
sessão (a própria caixa marca a 1ª como lida ao abrir) e o item seguinte era pulado.

Também cobre a leitura automática ao abrir a caixa (#17388): ela lê a primeira notificação
LEGÍVEL da lista, pulando as que têm bloqueio de leitura.
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

ROTA = '/comum/busca_notificacao/{ultimo_pk}/'


def _cliente_com_notificacoes(client: Client, quantidade: int) -> tuple[Client, list[RegistroNotificacao]]:
    """Servidor logado com ``quantidade`` não lidas, devolvidas na ordem da caixa (mais recente primeiro)."""
    user = ServidorFactory().get_user()
    vinculo = user.get_vinculo()
    client.force_login(user)
    for indice in range(quantidade):
        send_notification('Rolagem', f'Notificação {indice}.', settings.DEFAULT_FROM_EMAIL, [vinculo], categoria='Rolagem', so_notificar=True)
    return client, list(RegistroNotificacao.objects.filter(vinculo=vinculo).order_by('-data', '-pk'))


def test_cursor_devolve_a_ancora_seguinte_em_json(client: Client, sync_permissions) -> None:
    client, registros = _cliente_com_notificacoes(client, 2)
    resposta = client.get(ROTA.format(ultimo_pk=registros[0].pk))

    assert resposta.status_code == 200
    assert resposta['Content-Type'] == 'application/json'
    assert f'data-article="{registros[1].pk}"' in resposta.json()['itens'], 'o cursor não devolveu a notificação seguinte'


def test_cursor_no_ultimo_item_devolve_json_com_itens_vazio(client: Client, sync_permissions) -> None:
    client, registros = _cliente_com_notificacoes(client, 1)
    resposta = client.get(ROTA.format(ultimo_pk=registros[-1].pk))

    assert resposta.status_code == 200
    assert resposta['Content-Type'] == 'application/json', 'o fim da lista virou HTML e o $.ajax do cabeçalho cai no .fail()'
    assert resposta.json() == {'itens': ''}


def test_rolagem_nao_pula_item_depois_de_a_caixa_marcar_a_primeira_como_lida(client: Client, sync_permissions) -> None:
    client, registros = _cliente_com_notificacoes(client, 11)

    client.get('/comum/notificacoes/')  # exibe as 10 primeiras e marca a 1ª como lida
    assert RegistroNotificacao.objects.get(pk=registros[0].pk).lida
    resposta = client.get(ROTA.format(ultimo_pk=registros[9].pk))

    assert f'data-article="{registros[10].pk}"' in resposta.json()['itens'], 'a rolagem pulou a 11ª notificação'


def test_caixa_le_a_primeira_legivel_pulando_a_travada_mais_recente(client: Client, sync_permissions) -> None:
    """Uma travada no topo (ex.: alerta de dispositivo desconhecido, 3 dias de bloqueio) não impede a leitura das demais (#17388)."""
    client, (legivel, mais_antiga) = _cliente_com_notificacoes(client, 2)  # mais recente primeiro
    vinculo = legivel.vinculo
    send_notification(
        'Travada',
        'Notificação com bloqueio de leitura.',
        settings.DEFAULT_FROM_EMAIL,
        [vinculo],
        categoria='Travada',
        so_notificar=True,
        data_permite_marcar_lida=datetime.now() + timedelta(days=3),
    )
    travada = RegistroNotificacao.objects.filter(vinculo=vinculo).order_by('-data', '-pk').first()
    assert not travada.pode_ler(), 'pré-condição: a notificação mais recente deveria estar travada'

    client.get('/comum/notificacoes/')

    assert RegistroNotificacao.objects.get(pk=legivel.pk).lida, 'a travada no topo impediu a caixa de ler a primeira legível'
    assert not RegistroNotificacao.objects.get(pk=travada.pk).lida, 'a caixa marcou como lida uma notificação travada'
    assert not RegistroNotificacao.objects.get(pk=mais_antiga.pk).lida, 'a caixa marcou como lida mais de uma notificação'
