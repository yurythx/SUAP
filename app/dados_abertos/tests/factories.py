"""Factories factory_boy do app dados_abertos."""

from __future__ import annotations

import datetime

import factory
from factory.django import DjangoModelFactory

from dados_abertos.enums import FormatoRecurso, ResultadoAtualizacao, TipoEventoLAI
from dados_abertos.models import AtualizacaoBaseDados, BaseDados, DeliberacaoLAI, Licenca, Organizacao, PDABaseDados, PlanoDadosAbertos, RecursoDados


class OrganizacaoFactory(DjangoModelFactory):
    class Meta:
        model = Organizacao

    nome = factory.Sequence(lambda n: f'organizacao-{n}')
    titulo = factory.Sequence(lambda n: f'Organização {n}')


class BaseDadosFactory(DjangoModelFactory):
    class Meta:
        model = BaseDados

    nome = factory.Sequence(lambda n: f'base-{n}')
    titulo = factory.Sequence(lambda n: f'Base de dados {n}')


class LicencaFactory(DjangoModelFactory):
    class Meta:
        model = Licenca
        django_get_or_create = ('nome',)

    nome = factory.Sequence(lambda n: f'Licença {n}')
    codigo_ckan = 'cc-by'


class RecursoDadosFactory(DjangoModelFactory):
    """Recurso com arquivo já anexado: sem ``url``, o ``save()`` não tenta baixar nada."""

    class Meta:
        model = RecursoDados

    dataset = factory.SubFactory(BaseDadosFactory)
    nome = factory.Sequence(lambda n: f'Recurso {n}')
    formato = FormatoRecurso.CSV
    arquivo = factory.django.FileField(filename='recurso.csv', data=b'id,valor\n1,10\n')


class PlanoDadosAbertosFactory(DjangoModelFactory):
    class Meta:
        model = PlanoDadosAbertos

    titulo = factory.Sequence(lambda n: f'PDA {n}')
    vigencia_inicio = datetime.date(2000, 1, 1)
    vigencia_fim = datetime.date(2001, 12, 31)


class PDABaseDadosFactory(DjangoModelFactory):
    class Meta:
        model = PDABaseDados

    pda = factory.SubFactory(PlanoDadosAbertosFactory)
    base_dados = factory.SubFactory(BaseDadosFactory)


class DeliberacaoLAIFactory(DjangoModelFactory):
    """Evento automático da linha do tempo do LAI (sem autor)."""

    class Meta:
        model = DeliberacaoLAI

    pda_base_dados = factory.SubFactory(PDABaseDadosFactory)
    tipo = TipoEventoLAI.ENVIO


class AtualizacaoBaseDadosFactory(DjangoModelFactory):
    class Meta:
        model = AtualizacaoBaseDados

    base_dados = factory.SubFactory(BaseDadosFactory)
    resultado = ResultadoAtualizacao.SUCESSO
