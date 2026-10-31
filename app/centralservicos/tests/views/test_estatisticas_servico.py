"""A atualização manual das estatísticas recalcula o serviço numa tarefa em background (#17800).

Recalcula mesmo que o serviço não esteja pendente: quem clicou quer recalcular.
"""

from __future__ import annotations

import pytest
from django.test import Client

from centralservicos.models import Chamado, Servico, StatusChamado
from centralservicos.tests.factories import GestorAreaServicoFactory, ServicoFactory
from rh.tests.factories import ServidorFactory

pytestmark = pytest.mark.django_db

SENTINELA = 99


def test_gestor_pede_atualizacao_e_o_servico_e_recalculado(client: Client, sync_permissions) -> None:
    gestor = GestorAreaServicoFactory(gestor=ServidorFactory().get_user())
    servico = ServicoFactory(area=gestor.area)
    Servico.objects.filter(pk=servico.pk).update(estatisticas_pendentes=False, qtd_chamados_fechados=SENTINELA)
    client.force_login(gestor.gestor)

    resposta = client.post(f'/centralservicos/atualizar_estatisticas_servico/{servico.pk}/', {'confirmar': '1'})

    # A view devolve a tela de progresso da tarefa (em teste a tarefa roda na hora).
    assert resposta.status_code == 302
    assert resposta.headers['Location'].startswith('/djtools/process/')
    servico.refresh_from_db()
    assert not servico.estatisticas_pendentes
    assert servico.qtd_chamados_fechados == Chamado.objects.filter(servico=servico, status=StatusChamado.FECHADO).count()
