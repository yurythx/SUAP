# pyright: reportPrivateImportUsage=false, reportIncompatibleVariableOverride=false
"""Factories factory_boy de modelos do app ``projetos_ensino``."""

from __future__ import annotations

import datetime
from decimal import Decimal

import factory
from factory.django import DjangoModelFactory

from comum.tests.factories import AnoFactory
from djtools.utils import get_datetime_now
from projetos_ensino.models import AvaliadorIndicado, Desembolso, ProjetoCancelado, RegistroGasto


def _salvar_sem_argumentos(model_class: type, kwargs: dict) -> object:
    """``create`` para os models cujo ``save(self)`` não aceita argumentos (o do factory_boy passa ``force_insert``)."""
    objeto = model_class(**kwargs)
    objeto.save()
    return objeto


class DesembolsoFactory(DjangoModelFactory):
    """Desembolso de um item da memória de cálculo (projeto e despesa vêm do item). Informe ``item``."""

    class Meta:
        model = Desembolso

    projeto = factory.LazyAttribute(lambda desembolso: desembolso.item.projeto)
    ano = factory.SubFactory(AnoFactory)
    mes = 1
    valor = Decimal('100')

    @classmethod
    def _create(cls, model_class: type[Desembolso], *args: object, **kwargs: object) -> Desembolso:
        return _salvar_sem_argumentos(model_class, kwargs)


class RegistroGastoFactory(DjangoModelFactory):
    """Gasto registrado contra um desembolso (ano, mês e item vêm dele), ainda sem avaliação. Informe ``desembolso``."""

    class Meta:
        model = RegistroGasto

    ano = factory.LazyAttribute(lambda registro: registro.desembolso.ano)
    mes = factory.LazyAttribute(lambda registro: registro.desembolso.mes)
    descricao = factory.Sequence(lambda n: f'Gasto registrado {n}')
    qtd = 1
    valor_unitario = Decimal('100')
    data_cadastro = factory.LazyFunction(datetime.date.today)

    @classmethod
    def _create(cls, model_class: type[RegistroGasto], *args: object, **kwargs: object) -> RegistroGasto:
        return _salvar_sem_argumentos(model_class, kwargs)


class ProjetoCanceladoFactory(DjangoModelFactory):
    """Pedido de cancelamento ainda não avaliado. Informe ``projeto``."""

    class Meta:
        model = ProjetoCancelado

    justificativa_cancelamento = 'Coordenador afastado'
    data_solicitacao = factory.LazyFunction(get_datetime_now)


class AvaliadorIndicadoFactory(DjangoModelFactory):
    """Indicação de avaliador para o projeto. Informe ``projeto`` e ``vinculo``."""

    class Meta:
        model = AvaliadorIndicado
