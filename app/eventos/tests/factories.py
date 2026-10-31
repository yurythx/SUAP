# pyright: reportPrivateImportUsage=false, reportIncompatibleVariableOverride=false
"""Factories factory_boy de modelos do app ``eventos``."""

from __future__ import annotations

import datetime

import factory
from factory.django import DjangoModelFactory

from eventos.models import (
    AreaTematica,
    AutorSubmissao,
    Dimensao,
    Evento,
    Modalidade,
    Participante,
    PublicoAlvoEvento,
    Submissao,
    TipoModalidade,
    TipoParticipacao,
    TipoParticipante,
)
from rh.tests.factories import SetorFactory, cpf_valido


class PublicoAlvoEventoFactory(DjangoModelFactory):
    """Tabela-tipo: os ids são as constantes ``PublicoAlvoEvento.*``."""

    class Meta:
        model = PublicoAlvoEvento
        django_get_or_create = ('id',)

    id = PublicoAlvoEvento.PUBLICO_EXTERNO
    descricao = factory.LazyAttribute(lambda o: f'Público {o.id}')


class DimensaoFactory(DjangoModelFactory):
    """Tabela-tipo de dimensão do evento (Extensão, Pesquisa, Ensino)."""

    class Meta:
        model = Dimensao
        django_get_or_create = ('descricao',)

    descricao = 'Extensão'


class EventoFactory(DjangoModelFactory):
    class Meta:
        model = Evento

    nome = factory.Sequence(lambda n: f'Evento {n}')
    apresentacao = 'Apresentação do evento'
    local = 'Auditório'
    data_inicio = factory.LazyFunction(lambda: datetime.date.today() + datetime.timedelta(days=30))
    hora_inicio = datetime.time(8, 0)
    data_fim = factory.LazyAttribute(lambda o: o.data_inicio + datetime.timedelta(days=1))
    hora_fim = datetime.time(18, 0)
    gera_certificado = False
    campus = factory.LazyFunction(lambda: SetorFactory().uo)


class TipoParticipacaoFactory(DjangoModelFactory):
    class Meta:
        model = TipoParticipacao
        django_get_or_create = ('descricao',)

    descricao = 'Participante'


class TipoParticipanteFactory(DjangoModelFactory):
    class Meta:
        model = TipoParticipante

    evento = factory.SubFactory(EventoFactory)
    tipo_participacao = factory.SubFactory(TipoParticipacaoFactory)


class ParticipanteFactory(DjangoModelFactory):
    class Meta:
        model = Participante

    evento = factory.SubFactory(EventoFactory)
    tipo = factory.SubFactory(TipoParticipanteFactory, evento=factory.SelfAttribute('..evento'))
    nome = factory.Sequence(lambda n: f'Participante {n}')
    cpf = factory.Sequence(lambda n: cpf_valido(n + 700000))
    email = factory.Sequence(lambda n: f'participante{n}@example.com')


class TipoModalidadeFactory(DjangoModelFactory):
    class Meta:
        model = TipoModalidade

    titulo = factory.Sequence(lambda n: f'Tipo de modalidade {n}')


class ModalidadeFactory(DjangoModelFactory):
    class Meta:
        model = Modalidade

    tipo = factory.SubFactory(TipoModalidadeFactory)
    evento = factory.SubFactory(EventoFactory)
    tipo_submissao = 'TEX'
    limite_submissoes = 10


class AreaTematicaFactory(DjangoModelFactory):
    class Meta:
        model = AreaTematica

    titulo = factory.Sequence(lambda n: f'Área temática {n}')


class SubmissaoFactory(DjangoModelFactory):
    class Meta:
        model = Submissao

    titulo = factory.Sequence(lambda n: f'Trabalho {n}')
    modalidade = factory.SubFactory(ModalidadeFactory)
    area_tematica = factory.SubFactory(AreaTematicaFactory)


class AutorSubmissaoFactory(DjangoModelFactory):
    class Meta:
        model = AutorSubmissao

    submissao = factory.SubFactory(SubmissaoFactory)
    participante = factory.SubFactory(ParticipanteFactory, evento=factory.SelfAttribute('..submissao.modalidade.evento'))


class AvaliadorModalidadeFactory(DjangoModelFactory):
    class Meta:
        model = 'eventos.AvaliadorModalidade'

    modalidade = factory.SubFactory(ModalidadeFactory)
    avaliador = factory.SubFactory(ParticipanteFactory, evento=factory.SelfAttribute('..modalidade.evento'))


class VersaoSubmissaoFactory(DjangoModelFactory):
    class Meta:
        model = 'eventos.VersaoSubmissao'

    submissao = factory.SubFactory(SubmissaoFactory)
    numero = 2


class AvaliacaoSubmissaoFactory(DjangoModelFactory):
    class Meta:
        model = 'eventos.AvaliacaoSubmissao'

    versao = factory.SubFactory(VersaoSubmissaoFactory)
    avaliador_modalidade = factory.SubFactory(AvaliadorModalidadeFactory, modalidade=factory.SelfAttribute('..versao.submissao.modalidade'))


class FluxoSubmissaoFactory(DjangoModelFactory):
    class Meta:
        model = 'eventos.FluxoSubmissao'

    evento = factory.SubFactory(EventoFactory)
    etapa = 'REF'
    data_inicio = factory.LazyFunction(datetime.date.today)
