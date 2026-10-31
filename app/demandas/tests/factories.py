# pyright: reportPrivateImportUsage=false, reportIncompatibleVariableOverride=false
"""Factories factory_boy do app demandas.

Cobre a demanda e seu ciclo (consolidação, especificação, revisão, entrega), a área de
atuação do módulo, as tags e a sugestão de melhoria.

As factories de modelos de **outros apps** moram no app dono e são reusadas aqui:
``UserFactory`` e ``AreaAtuacaoFactory`` em ``comum.tests.factories``.

Duas ressalvas do domínio, ambas deliberadas:

* ``SugestaoMelhoria.requisitante`` é um ``CurrentUserField`` — sem valor explícito ele
  puxa o usuário do threadlocal, que em teste costuma ser anônimo. A factory sempre
  informa um ``requisitante``. O ``save()`` da sugestão ainda grava o histórico com
  ``tl.get_user()``, então o teste continua precisando do threadlocal preenchido.
* ``AmbienteHomologacao.save()`` cria um pipeline no GitLab quando ``pipeline`` é nulo; a
  factory sempre preenche o ``pipeline``, então criar o ambiente não sai do banco.
* ``Demanda.save()``/``alterar_situacao`` falam com e-mail e GitLab. Isolar isso é papel
  da fixture autouse ``sem_efeitos_externos`` (``demandas/tests/conftest.py``), não da
  factory.
"""

from __future__ import annotations

from datetime import date, timedelta

import factory
from factory.django import DjangoModelFactory

from comum.tests.factories import AreaAtuacaoFactory, UserFactory

from demandas.models import (
    AmbienteHomologacao,
    AnalistaDesenvolvedor,
    AreaAtuacaoDemanda,
    Demanda,
    DoD,
    Entrega,
    Especificacao,
    RevisaoEspecificacao,
    SugestaoMelhoria,
    Tag,
)
from demandas.models.demanda import Situacao
from demandas.models.entrega import StatusEntrega


class TagFactory(DjangoModelFactory):
    class Meta:
        model = Tag
        django_get_or_create = ('nome',)

    nome = factory.Sequence(lambda n: f'Módulo {n}')


class AreaAtuacaoDemandaFactory(DjangoModelFactory):
    """Área do módulo. ``area`` é ``OneToOne``: cada chamada cria uma ``AreaAtuacao`` nova."""

    class Meta:
        model = AreaAtuacaoDemanda

    area = factory.SubFactory(AreaAtuacaoFactory)


class DemandaFactory(DjangoModelFactory):
    """Demanda recém-aberta (nasce em ``ESTADO_ABERTO`` / 'Solicitada'), sem área."""

    class Meta:
        model = Demanda

    titulo = factory.Sequence(lambda n: f'Demanda {n}')
    descricao = 'Descrição pública da demanda.'
    situacao = Situacao.ESTADO_ABERTO


class DoDFactory(DjangoModelFactory):
    """Consolidação da demanda."""

    class Meta:
        model = DoD

    demanda = factory.SubFactory(DemandaFactory)
    descricao = 'Consolidação'


class EspecificacaoFactory(DjangoModelFactory):
    class Meta:
        model = Especificacao

    dod = factory.SubFactory(DoDFactory)
    nome = factory.Sequence(lambda n: f'Especificação {n}')
    ordem = factory.Sequence(lambda n: n + 1)


class RevisaoEspecificacaoFactory(DjangoModelFactory):
    """Revisão de especificação. Sem ``especificacao``, representa uma inclusão proposta."""

    class Meta:
        model = RevisaoEspecificacao

    dod = factory.SubFactory(DoDFactory)
    nome = factory.Sequence(lambda n: f'Especificação revisada {n}')


class EntregaFactory(DjangoModelFactory):
    class Meta:
        model = Entrega

    demanda = factory.SubFactory(DemandaFactory)
    titulo = factory.Sequence(lambda n: f'Pacote {n}')
    status = StatusEntrega.ENVIADA
    cadastrada_por = factory.SubFactory(UserFactory)


class SugestaoMelhoriaFactory(DjangoModelFactory):
    class Meta:
        model = SugestaoMelhoria

    area_atuacao = factory.SubFactory(AreaAtuacaoDemandaFactory)
    requisitante = factory.SubFactory(UserFactory)
    titulo = factory.Sequence(lambda n: f'Sugestão {n}')
    descricao = 'Descrição da sugestão.'


class AnalistaDesenvolvedorFactory(DjangoModelFactory):
    class Meta:
        model = AnalistaDesenvolvedor

    usuario = factory.SubFactory(UserFactory)
    username_gitlab = factory.Sequence(lambda n: f'dev{n}')


class AmbienteHomologacaoFactory(DjangoModelFactory):
    class Meta:
        model = AmbienteHomologacao

    criador = factory.SubFactory(AnalistaDesenvolvedorFactory)
    branch = factory.Sequence(lambda n: f'demanda_{n}')
    data_criacao = factory.LazyFunction(date.today)
    data_expiracao = factory.LazyFunction(lambda: date.today() + timedelta(days=7))
    senha = '123'
    pipeline = factory.Sequence(lambda n: 1000 + n)
    url_gitlab = factory.LazyAttribute(lambda o: f'https://gitlab.exemplo/-/pipelines/{o.pipeline}')
    ativo = True
