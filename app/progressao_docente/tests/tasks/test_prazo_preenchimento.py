"""Testes da transição automática por prazo de preenchimento (erro-10030).

Regra: uma Avaliacao em AGUARDANDO_PREENCHIMENTO cujo prazo
(data_liberacao_preenchimento + tempo_preenchimento) venceu deve ser tramitada
automaticamente para EM_AVALIACAO pelo command `processar_prazos_avaliacao`,
mesmo sem preenchimento do avaliado.
"""

from datetime import datetime, timedelta

import pytest
from django.apps.registry import apps
from django.core.management import call_command

from progressao_docente.tests.factories import AvaliacaoFactory, ProgressaoDocenteFactory
from rh.tests.factories import ServidorFactory

ProgressaoDocente = apps.get_model('progressao_docente', 'ProgressaoDocente')
Avaliacao = apps.get_model('progressao_docente', 'Avaliacao')

pytestmark = pytest.mark.django_db


def _criar_avaliacao(*, dias_atras, situacao=None):
    progressao = ProgressaoDocenteFactory(situacao=ProgressaoDocente.AGUARDANDO_PREENCHIMENTO)
    avaliacao = AvaliacaoFactory(
        progressao=progressao,
        situacao=situacao or Avaliacao.AGUARDANDO_PREENCHIMENTO,
        data_liberacao_preenchimento=datetime.now() - timedelta(days=dias_atras),
    )
    avaliacao.avaliadores.add(ServidorFactory())
    return avaliacao, progressao


def test_prazo_vencido_transita_para_em_avaliacao(sync_permissions):
    # prazo padrão é 30 dias; 40 dias atrás => vencido
    avaliacao, progressao = _criar_avaliacao(dias_atras=40)

    call_command('processar_prazos_avaliacao')

    avaliacao.refresh_from_db()
    progressao.refresh_from_db()
    assert avaliacao.situacao == Avaliacao.EM_AVALIACAO
    assert avaliacao.preenchimento_expirado is True
    assert avaliacao.preenchida is False
    assert avaliacao.data_liberacao_avaliacao is not None
    # o processo deve acompanhar (todas as avaliações em EM_AVALIACAO)
    assert progressao.situacao == ProgressaoDocente.EM_AVALIACAO


def test_prazo_nao_vencido_permanece_aguardando(sync_permissions):
    avaliacao, _ = _criar_avaliacao(dias_atras=5)

    call_command('processar_prazos_avaliacao')

    avaliacao.refresh_from_db()
    assert avaliacao.situacao == Avaliacao.AGUARDANDO_PREENCHIMENTO
    assert avaliacao.preenchimento_expirado is False


def test_idempotente_nao_reprocessa(sync_permissions):
    avaliacao, _ = _criar_avaliacao(dias_atras=40)

    call_command('processar_prazos_avaliacao')
    call_command('processar_prazos_avaliacao')  # segunda execução não deve alterar/duplicar

    avaliacao.refresh_from_db()
    assert avaliacao.situacao == Avaliacao.EM_AVALIACAO
