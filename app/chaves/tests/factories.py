"""Factories dos models do app ``chaves``."""

from __future__ import annotations

import factory
from factory.django import DjangoModelFactory

from chaves.models import Chave
from comum.tests.factories import SalaFactory


class ChaveFactory(DjangoModelFactory):
    """Chave de uma sala, sem pessoas permitidas."""

    class Meta:
        model = Chave

    identificacao = factory.Sequence(lambda n: f'CHAVE-{n}')
    sala = factory.SubFactory(SalaFactory)
