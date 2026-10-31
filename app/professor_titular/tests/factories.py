# pyright: reportPrivateImportUsage=false, reportIncompatibleVariableOverride=false
"""Factories factory_boy de modelos do app ``professor_titular``."""

import factory
from factory.django import DjangoModelFactory

from djtools.utils import get_datetime_now
from professor_titular.models import CategoriaMemorialDescritivo, Criterio, Grupo, Indicador, PontuacaoMinima, ProcessoTitular, Unidade
from rh.tests.factories import ServidorFactory


class ProcessoTitularFactory(DjangoModelFactory):
    """Processo aguardando a seleção da banca. O ``ServidorFactory`` exige a fixture ``sync_permissions``."""

    class Meta:
        model = ProcessoTitular

    servidor = factory.SubFactory(ServidorFactory)
    ano = factory.LazyFunction(lambda: get_datetime_now().year)
    status = ProcessoTitular.STATUS_AGUARDANDO_AVALIADORES


class GrupoFactory(DjangoModelFactory):
    class Meta:
        model = Grupo

    nome = factory.Sequence(lambda n: f'Grupo {n}')
    percentual = 100


class PontuacaoMinimaFactory(DjangoModelFactory):
    class Meta:
        model = PontuacaoMinima

    grupo = factory.SubFactory(GrupoFactory)
    ano = factory.LazyFunction(lambda: get_datetime_now().year)
    pontuacao_exigida = 100
    qtd_minima_grupos = 1


class IndicadorFactory(DjangoModelFactory):
    class Meta:
        model = Indicador

    grupo = factory.SubFactory(GrupoFactory)
    nome = factory.Sequence(lambda n: f'Indicador {n}')
    descricao = 'Indicador'


class UnidadeFactory(DjangoModelFactory):
    class Meta:
        model = Unidade
        django_get_or_create = ('nome',)

    nome = 'Unidade'
    sigla = 'UN'


class CategoriaMemorialDescritivoFactory(DjangoModelFactory):
    class Meta:
        model = CategoriaMemorialDescritivo

    nome = 'Itinerário de formação'
    indice = 'c'


class CriterioFactory(DjangoModelFactory):
    class Meta:
        model = Criterio

    indicador = factory.SubFactory(IndicadorFactory)
    artigo = 'Art. 1'
    nome = 'Critério'
    status = Criterio.STATUS_ATIVO
    pontos = 1
    unidade = factory.SubFactory(UnidadeFactory)
    categoria_memorial_descritivo = factory.SubFactory(CategoriaMemorialDescritivoFactory)
    num_artigo = 1
    inciso = 'I'
    alinea = 'a'
