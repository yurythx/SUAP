# pyright: reportPrivateImportUsage=false, reportIncompatibleVariableOverride=false
"""Factories factory_boy do app progressao_docente.

Cobre o formulário, a progressão e a avaliação — o trio que quase todo teste do módulo
monta. As factories de modelos de **outros apps** moram no app dono e são reusadas aqui:
``ServidorFactory`` em ``rh.tests.factories``.

Atenção ao custo e a uma dependência herdados do ``ServidorFactory``: ele cria ``User`` e
``Vinculo``, custa ~140 ms e o seu ``save`` busca grupos por nome, então **todo teste que
construir uma progressão precisa da fixture ``sync_permissions``**. Quando o teste não se
importa com quem é o avaliado, um ``ServidorFactory`` compartilhado entre as progressões
sai bem mais barato que um por progressão.
"""

from __future__ import annotations

from datetime import date

import factory
from factory.django import DjangoModelFactory

from rh.tests.factories import ServidorFactory

from progressao_docente.models import Avaliacao, AvaliacaoItem, Criterio, DocenteAProgredir, Formulario, Item, ProgressaoDocente


class FormularioFactory(DjangoModelFactory):
    class Meta:
        model = Formulario

    nome = factory.Sequence(lambda n: f'Formulário {n}')
    inicio_vigencia = date(2026, 1, 1)


class ProgressaoDocenteFactory(DjangoModelFactory):
    """Progressão recém-aberta (``A_INICIAR``) de um servidor novo."""

    class Meta:
        model = ProgressaoDocente

    avaliado = factory.SubFactory(ServidorFactory)
    data_inicio_periodo = date(2026, 1, 1)
    situacao = ProgressaoDocente.A_INICIAR


class DocenteAProgredirFactory(DjangoModelFactory):
    """Interstício de 24 meses ainda sem progressão criada."""

    class Meta:
        model = DocenteAProgredir

    avaliado = factory.SubFactory(ServidorFactory)
    data_inicio_contagem = date(2024, 6, 11)
    data_fim_contagem = date(2026, 6, 10)
    nivel_atual = 'C2'
    proximo_nivel = 'C3'


class AvaliacaoFactory(DjangoModelFactory):
    """Avaliação aguardando preenchimento. Sem ``data_liberacao_*``: quem testa prazo informa."""

    class Meta:
        model = Avaliacao

    progressao = factory.SubFactory(ProgressaoDocenteFactory)
    formulario = factory.SubFactory(FormularioFactory)
    situacao = Avaliacao.AGUARDANDO_PREENCHIMENTO


class CriterioFactory(DjangoModelFactory):
    class Meta:
        model = Criterio

    formulario = factory.SubFactory(FormularioFactory)
    order = factory.Sequence(lambda n: str(n + 1))
    nome = factory.Sequence(lambda n: f'Critério {n}')
    inicio_vigencia = date(2026, 1, 1)


class ItemFactory(DjangoModelFactory):
    class Meta:
        model = Item

    criterio = factory.SubFactory(CriterioFactory)
    nome = factory.Sequence(lambda n: f'Item {n}')
    inicio_vigencia = date(2026, 1, 1)


class AvaliacaoItemFactory(DjangoModelFactory):
    """Item respondido de uma avaliação.

    ``avaliacao`` e ``item`` vêm de sub-factories independentes: quem precisa que o item
    pertença ao formulário da avaliação (o caso comum) informa os dois.
    """

    class Meta:
        model = AvaliacaoItem

    avaliacao = factory.SubFactory(AvaliacaoFactory)
    item = factory.SubFactory(ItemFactory)
