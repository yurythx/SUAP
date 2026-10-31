# pyright: reportPrivateImportUsage=false, reportIncompatibleVariableOverride=false
"""Factories factory_boy de modelos do app ``progressoes``."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import factory
from factory.django import DjangoModelFactory

from djtools.utils import get_datetime_now
from progressoes.models import ConfiguracaoProgressao, ProcessoProgressao, ServidorAProgredir, SiglaSetorPrimeiroTramite
from rh.tests.factories import ServidorFactory


def _hoje() -> date:
    return get_datetime_now().date()


class ConfiguracaoProgressaoFactory(DjangoModelFactory):
    """Configuração ativa da progressão TAE (o ``save`` desativa as demais)."""

    class Meta:
        model = ConfiguracaoProgressao

    intersticio_progressao = 18
    intersticio_estagio_probatorio = 36
    dias_antecedencia_calcular = 90
    gerar_inconsistencia_dias = 90
    media_aprovacao = Decimal('60.0')
    ativo = True


class ServidorAProgredirFactory(DjangoModelFactory):
    """Registro do relatório de servidores a progredir, ainda sem processo criado.

    Informe ``avaliado`` quando o teste depender do setor dele; o ``ServidorFactory``
    exige a fixture ``sync_permissions``.
    """

    class Meta:
        model = ServidorAProgredir

    avaliado = factory.SubFactory(ServidorFactory)
    data_fim_contagem = factory.LazyFunction(lambda: _hoje() + timedelta(days=90))
    data_inicio_contagem = factory.LazyAttribute(lambda o: o.data_fim_contagem - timedelta(days=540))


class ProcessoProgressaoFactory(DjangoModelFactory):
    """Processo de progressão por mérito a iniciar.

    O ``save`` de criação recalcula a data final (afastamentos e saldo): exige uma
    ``ConfiguracaoProgressaoFactory`` ativa. Informada a ``data_fim_contagem_progressao``,
    ela é mantida quando o avaliado não tem afastamentos.
    """

    class Meta:
        model = ProcessoProgressao

    avaliado = factory.SubFactory(ServidorFactory)
    data_fim_contagem_progressao = factory.LazyFunction(lambda: _hoje() + timedelta(days=90))
    data_inicio_contagem_progressao = factory.LazyAttribute(lambda o: o.data_fim_contagem_progressao - timedelta(days=540))


class SiglaSetorPrimeiroTramiteFactory(DjangoModelFactory):
    """Sigla de setor de primeiro trâmite do campus; informe ``tipo`` para a reitoria e ``ordem`` para a precedência."""

    class Meta:
        model = SiglaSetorPrimeiroTramite

    tipo = SiglaSetorPrimeiroTramite.TIPO_CAMPUS
    sigla = factory.Sequence(lambda n: f'SIGLA{n}')
    ordem = factory.Sequence(lambda n: n + 1)
