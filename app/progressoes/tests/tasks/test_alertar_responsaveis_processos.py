"""Comando ``alertar_responsaveis_processos``: avisa o setor de primeiro trâmite das progressões a iniciar."""

from datetime import date, timedelta

import pytest
from django.core.management import call_command

from comum.models import Configuracao, RegistroNotificacao
from djtools.utils import get_datetime_now
from progressoes.models import ProcessoProgressao
from progressoes.tests.factories import (
    ConfiguracaoProgressaoFactory,
    ProcessoProgressaoFactory,
    ServidorAProgredirFactory,
    SiglaSetorPrimeiroTramiteFactory,
)
from rh.models import Servidor, Setor
from rh.tests.factories import ServidorFactory, SetorFactory

pytestmark = pytest.mark.django_db

ASSUNTO = 'Processo de Progressão a Iniciar Identificado'


def _hoje() -> date:
    return get_datetime_now().date()


def _notificados(servidor: Servidor) -> int:
    return RegistroNotificacao.objects.filter(vinculo=servidor.get_vinculo(), notificacao__categoria__assunto=ASSUNTO).count()


@pytest.fixture
def campus(sync_permissions: None) -> Setor:
    """Campus com alertas ligados e o setor de primeiro trâmite (COGPE) configurado."""
    Configuracao.objects.filter(app='progressoes').delete()
    Configuracao.objects.create(app='progressoes', chave='alertar_responsaveis_servidores_a_progredir', valor='True')
    Configuracao.clear_cache()
    SiglaSetorPrimeiroTramiteFactory(sigla='COGPE')
    return SetorFactory(sigla='CAMPUS1')


@pytest.mark.parametrize(
    ('dias_para_fim', 'saldo_dias'),
    [(40, 20), (10, 60)],
    ids=['prazo_com_saldo_em_menos_de_30_dias', 'prazo_com_saldo_vencido'],
)
def test_saldo_antecipa_o_prazo_do_aviso_do_servidor_a_progredir(campus: Setor, dias_para_fim: int, saldo_dias: int) -> None:
    responsavel = ServidorFactory(setor=SetorFactory(sigla='COGPE/CAMPUS1', superior=campus))
    ServidorAProgredirFactory(
        avaliado=ServidorFactory(setor=SetorFactory(superior=campus)),
        data_fim_contagem=_hoje() + timedelta(days=dias_para_fim),
        saldo_dias=saldo_dias,
        notificado_45_dias=True,
    )

    call_command('alertar_responsaveis_processos')

    assert _notificados(responsavel) == 1


def test_aviso_antecipado_unico_chega_a_todo_o_setor(campus: Setor) -> None:
    cogpe = SetorFactory(sigla='COGPE/CAMPUS1', superior=campus)
    responsaveis = [ServidorFactory(setor=cogpe), ServidorFactory(setor=cogpe)]
    registro = ServidorAProgredirFactory(
        avaliado=ServidorFactory(setor=SetorFactory(superior=campus)),
        data_fim_contagem=_hoje() + timedelta(days=60),
    )

    call_command('alertar_responsaveis_processos')
    call_command('alertar_responsaveis_processos')

    assert [_notificados(r) for r in responsaveis] == [1, 1]
    registro.refresh_from_db()
    assert registro.notificado_45_dias


def test_processo_a_iniciar_vencido_avisa_o_setor(campus: Setor) -> None:
    ConfiguracaoProgressaoFactory()
    responsavel = ServidorFactory(setor=SetorFactory(sigla='COGPE/CAMPUS1', superior=campus))
    ProcessoProgressaoFactory(
        avaliado=ServidorFactory(setor=SetorFactory(superior=campus)),
        data_fim_contagem_progressao=_hoje() - timedelta(days=5),
        status=ProcessoProgressao.STATUS_A_INICIAR,
    )

    call_command('alertar_responsaveis_processos')

    assert _notificados(responsavel) == 1
