"""Estatísticas do serviço recalculadas fora do fechamento do chamado (#17800).

Fechar um chamado só marca o serviço como pendente; o comando manual
``centralservicos_atualizar_estatisticas_servicos`` recalcula os pendentes.
"""

from __future__ import annotations

import re
from unittest import mock

import pytest
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext

from centralservicos.models import Chamado, Servico, StatusChamado
from centralservicos.tests.builders import CentralServicosContext
from centralservicos.tests.factories import ServicoFactory

COMANDO = 'centralservicos_atualizar_estatisticas_servicos'
# Valor que o recálculo nunca produz neste cenário: se continuar lá, o serviço não foi recalculado.
SENTINELA = 99


@pytest.fixture
def contexto(centralservicos_context: CentralServicosContext) -> CentralServicosContext:
    # Serviço novo nasce pendente (default=True); parte de um serviço já calculado.
    Servico.objects.filter(pk=centralservicos_context.servico.pk).update(estatisticas_pendentes=False, qtd_chamados_fechados=SENTINELA)
    return centralservicos_context


def _fechar(contexto: CentralServicosContext) -> None:
    atendente = contexto.servidor_atendente.get_user()
    chamado = contexto.chamado
    chamado.colocar_em_atendimento(atendente)
    chamado.resolver_chamado(atendente, bases_conhecimento=[])
    chamado.fechar_chamado(atendente)


def _servico(contexto: CentralServicosContext) -> Servico:
    return Servico.objects.get(pk=contexto.servico.pk)


def test_fechar_chamado_marca_o_servico_pendente_sem_recalcular(contexto: CentralServicosContext) -> None:
    _fechar(contexto)

    servico = _servico(contexto)
    assert servico.estatisticas_pendentes
    assert servico.qtd_chamados_fechados == SENTINELA


def test_comando_recalcula_o_servico_pendente_e_limpa_a_marca(contexto: CentralServicosContext) -> None:
    _fechar(contexto)

    call_command(COMANDO)

    servico = _servico(contexto)
    assert not servico.estatisticas_pendentes
    assert servico.qtd_chamados_fechados == Chamado.objects.filter(servico=servico, status=StatusChamado.FECHADO).count()


def test_comando_nao_recalcula_servico_sem_pendencia(contexto: CentralServicosContext) -> None:
    call_command(COMANDO)

    assert _servico(contexto).qtd_chamados_fechados == SENTINELA


def test_comando_atualiza_so_os_campos_de_estatistica(contexto: CentralServicosContext) -> None:
    Servico.objects.filter(pk=contexto.servico.pk).update(estatisticas_pendentes=True)

    with CaptureQueriesContext(connection) as queries:
        call_command(COMANDO)

    updates = [set(re.findall(r'(?:SET |, )"(\w+)" = ', q['sql'])) for q in queries if q['sql'].startswith('UPDATE "centralservicos_servico"')]
    # A reivindicação limpa só a marca; o save do recálculo grava só as estatísticas, sem tocar na marca.
    assert updates == [{'estatisticas_pendentes'}, set(Servico.get_attrs_estatisticas())]
    assert 'estatisticas_pendentes' not in Servico.get_attrs_estatisticas()


_processar_chamados_original = Servico._processar_chamados


def test_fechamento_durante_o_recalculo_deixa_o_servico_pendente(contexto: CentralServicosContext) -> None:
    Servico.objects.filter(pk=contexto.servico.pk).update(estatisticas_pendentes=True)

    def fechamento_no_meio(servico: Servico, bloquear_db_obj: bool) -> list[Chamado.ChamadoEstatisticas]:
        # Depois da reivindicação e antes do save: o sinal de um fechamento remarca o serviço.
        Servico.objects.get(pk=servico.pk).anular_estatisticas()
        return _processar_chamados_original(servico, bloquear_db_obj)

    with mock.patch.object(Servico, '_processar_chamados', staticmethod(fechamento_no_meio)):
        call_command(COMANDO)

    servico = _servico(contexto)
    assert servico.estatisticas_pendentes
    assert servico.qtd_chamados_fechados == Chamado.objects.filter(servico=servico, status=StatusChamado.FECHADO).count()


def test_falha_num_servico_devolve_a_marca_e_segue_para_o_proximo(contexto: CentralServicosContext) -> None:
    outro = ServicoFactory()
    Servico.objects.filter(pk__in=[contexto.servico.pk, outro.pk]).update(estatisticas_pendentes=True, qtd_chamados_fechados=SENTINELA)

    def falha_no_primeiro(servico: Servico, bloquear_db_obj: bool) -> list[Chamado.ChamadoEstatisticas]:
        if servico.pk == contexto.servico.pk:
            raise RuntimeError('falha simulada')
        return _processar_chamados_original(servico, bloquear_db_obj)

    with mock.patch.object(Servico, '_processar_chamados', staticmethod(falha_no_primeiro)):
        call_command(COMANDO)

    falhou = _servico(contexto)
    assert falhou.estatisticas_pendentes
    assert falhou.qtd_chamados_fechados == SENTINELA
    seguiu = Servico.objects.get(pk=outro.pk)
    assert not seguiu.estatisticas_pendentes
    assert seguiu.qtd_chamados_fechados == Chamado.objects.filter(servico=seguiu, status=StatusChamado.FECHADO).count()
