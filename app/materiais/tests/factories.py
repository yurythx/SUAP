"""Factories do materiais: catálogo de materiais."""

import factory
from factory.django import DjangoModelFactory

from financeiro.tests.factories import SubElementoNaturezaDespesaFactory
from materiais import models


class UnidadeMedidaFactory(DjangoModelFactory):
    class Meta:
        model = models.UnidadeMedida
        django_get_or_create = ('descricao',)

    descricao = 'Unidade'


class CategoriaFactory(DjangoModelFactory):
    class Meta:
        model = models.Categoria

    sub_elemento_nd = factory.SubFactory(SubElementoNaturezaDespesaFactory)
    descricao = factory.Sequence(lambda n: f'Categoria {n}')
    codigo = factory.Sequence(lambda n: f'{n:04d}')


class MaterialFactory(DjangoModelFactory):
    class Meta:
        model = models.Material

    categoria = factory.SubFactory(CategoriaFactory)
    unidade_medida = factory.SubFactory(UnidadeMedidaFactory)
    codigo_catmat = factory.Sequence(lambda n: f'{n:06d}')
    descricao = factory.Sequence(lambda n: f'Material {n}')
    especificacao = 'Especificação'
