# pyright: reportPrivateImportUsage=false, reportIncompatibleVariableOverride=false
"""Factories factory_boy dos modelos do app ``ferias``.

Reutilizáveis por testes de qualquer app (o dono do modelo provê a factory).

``Ferias`` é única por (``servidor``, ``ano``) e o ``servidor`` vem do substrato
(fixture ``suap_data``), então o chamador sempre informa o servidor. As parcelas
carregam as datas que os outros módulos consomem — é ``ParcelaFerias``, não
``Ferias``, que responde "quando o servidor esteve de férias".
"""

from __future__ import annotations

import factory
from factory.django import DjangoModelFactory

from comum.tests.factories import AnoFactory
from ferias.models import Ferias, ParcelaFerias


class FeriasFactory(DjangoModelFactory):
    class Meta:
        model = Ferias
        django_get_or_create = ('servidor', 'ano')

    # servidor: informado pelo chamador (vem do substrato ``suap_data``).
    ano = factory.SubFactory(AnoFactory)
    validado = Ferias.VALIDADO


class ParcelaFeriasFactory(DjangoModelFactory):
    class Meta:
        model = ParcelaFerias
        django_get_or_create = ('ferias', 'numero_parcela')

    ferias = factory.SubFactory(FeriasFactory)
    numero_parcela = factory.Sequence(lambda n: str(n + 1))
    # data_inicio / data_fim: informados pelo chamador.
