# pyright: reportPrivateImportUsage=false, reportIncompatibleVariableOverride=false
"""Factories factory_boy de modelos do app ``avaliacao_integrada``."""

from __future__ import annotations

import datetime

import factory
from factory.django import DjangoModelFactory

from avaliacao_integrada.models import Avaliacao, Respondente, Segmento
from comum.tests.factories import AnoFactory
from rh.tests.factories import SetorFactory


class SegmentoFactory(DjangoModelFactory):
    """Tabela-tipo de segmentos respondentes."""

    class Meta:
        model = Segmento
        django_get_or_create = ('id',)

    id = Segmento.ESTUDANTE
    descricao = 'Estudante'
    tipo = Segmento.TIPO_PUBLICO_INTERNO


class AvaliacaoFactory(DjangoModelFactory):
    """Avaliação institucional."""

    class Meta:
        model = Avaliacao

    ano = factory.SubFactory(AnoFactory)
    nome = factory.Sequence(lambda n: f'Avaliação {n}')
    descricao = 'Descrição da avaliação institucional.'
    data_inicio = factory.LazyFunction(datetime.date.today)
    data_termino = factory.LazyFunction(lambda: datetime.date.today() + datetime.timedelta(days=30))


class RespondenteFactory(DjangoModelFactory):
    """Respondente vinculado a uma avaliação e segmento."""

    class Meta:
        model = Respondente

    avaliacao = factory.SubFactory(AvaliacaoFactory)
    segmento = factory.SubFactory(SegmentoFactory)
    uo = factory.LazyFunction(lambda: SetorFactory().uo)
