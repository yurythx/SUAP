# pyright: reportPrivateImportUsage=false, reportIncompatibleVariableOverride=false
"""Factories factory_boy de modelos do app ``pesquisa``."""

from __future__ import annotations

import factory
from factory.django import DjangoModelFactory

from djtools.utils import get_datetime_now
from pesquisa.models import ProjetoCancelado, RecursoProjeto


class ProjetoCanceladoFactory(DjangoModelFactory):
    """Pedido de cancelamento ainda não avaliado. Informe ``projeto``."""

    class Meta:
        model = ProjetoCancelado

    justificativa_cancelamento = 'Coordenador afastado'
    data_solicitacao = factory.LazyFunction(get_datetime_now)


class RecursoProjetoFactory(DjangoModelFactory):
    """Recurso contra a pré-seleção ainda não avaliado. Informe ``projeto``."""

    class Meta:
        model = RecursoProjeto

    justificativa = 'Projeto atende ao edital'
    data_solicitacao = factory.LazyFunction(get_datetime_now)
