"""Painel de indicadores de benefícios sem nenhum benefício cadastrado.

``generate_chart_evolucao_por_tipo`` montava o DataFrame direto do queryset e lia
``df['ano']``; sem benefícios o DataFrame vem sem colunas e o painel respondia 500
(``KeyError: 'ano'``). Agora o gráfico mostra "Sem dados para exibir", como os demais.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Group
from django.test import Client
from django.urls import reverse

from auditoria.models import Beneficio
from rh.tests.factories import ServidorFactory

pytestmark = pytest.mark.django_db


def test_painel_sem_beneficios_responde_200(client: Client, sync_permissions) -> None:
    auditor = ServidorFactory().get_user()
    auditor.groups.add(*Group.objects.filter(name__in=['Auditor', 'Auditor Sistêmico']))
    client.force_login(auditor)
    assert not Beneficio.objects.exists()

    resposta = client.get(reverse('auditoria:dashboard_beneficios'))

    assert resposta.status_code == 200
    assert 'Sem dados para exibir' in resposta.content.decode()
