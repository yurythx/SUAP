"""Factories dos models do app ``ae``."""

from __future__ import annotations

import datetime

import factory
from factory.django import DjangoModelFactory

from ae.models import DemandaAluno, Inscricao, Programa
from edu.tests.factories import AlunoFactory
from rh.tests.factories import SetorFactory


class ProgramaFactory(DjangoModelFactory):
    """Programa de assistência estudantil sediado num campus próprio."""

    class Meta:
        model = Programa

    descricao = factory.Sequence(lambda n: f'Programa {n}')
    instituicao = factory.LazyFunction(lambda: SetorFactory().uo)


class InscricaoFactory(DjangoModelFactory):
    """Inscrição de aluno num programa, sem período de inscrição."""

    class Meta:
        model = Inscricao

    programa = factory.SubFactory(ProgramaFactory)
    aluno = factory.SubFactory(AlunoFactory)
    data_cadastro = factory.LazyFunction(datetime.datetime.now)
    motivo = 'Motivo'


class DemandaAlunoFactory(DjangoModelFactory):
    """Demanda de atendimento pelo id fixo do model (``DemandaAluno.ALMOCO``, ``CAFE`` …)."""

    class Meta:
        model = DemandaAluno
        django_get_or_create = ('id',)

    id = DemandaAluno.ALMOCO
    nome = factory.LazyAttribute(lambda o: f'Demanda {o.id}')
    descricao = factory.SelfAttribute('nome')
    custeio = DemandaAluno.SEM_CUSTEIO
