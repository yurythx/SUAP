# pyright: reportPrivateImportUsage=false, reportIncompatibleVariableOverride=false
"""Factories factory_boy de modelos do app ``remanejamento``.

As factories de modelos de **outros apps** moram no app dono (ex.: ``DocumentoTextoFactory``
em ``documento_eletronico.tests.factories``).
"""

from __future__ import annotations

import datetime

import factory
from factory.django import DjangoModelFactory

from remanejamento.models import Edital


class EditalFactory(DjangoModelFactory):
    """Edital de remoção interna (TAE) só com os campos obrigatórios preenchidos.

    As datas opcionais do cronograma (recursos, resultado parcial, homologação) ficam vazias:
    cada teste preenche as que importam.
    """

    class Meta:
        model = Edital

    titulo = factory.Sequence(lambda n: f'Edital de Remoção {n}')
    descricao = 'Edital de teste'
    categoria = Edital.TAE
    chave_hash = factory.Sequence(lambda n: f'chave-{n}')
    inicio_inscricoes = factory.LazyFunction(lambda: datetime.datetime.now() - datetime.timedelta(days=30))
    fim_inscricoes = factory.LazyFunction(lambda: datetime.datetime.now() - datetime.timedelta(days=20))
    inicio_resultados = factory.LazyFunction(lambda: datetime.datetime.now() - datetime.timedelta(days=1))
