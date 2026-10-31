"""Factories do financeiro: classificações orçamentárias usadas pelo planejamento."""

import factory
from factory.django import DjangoModelFactory

from financeiro import models


class ProgramaFactory(DjangoModelFactory):
    class Meta:
        model = models.Programa
        django_get_or_create = ('codigo', 'nome')

    codigo = '9999'
    nome = 'Programa de Demonstração'


class AcaoFactory(DjangoModelFactory):
    class Meta:
        model = models.Acao
        django_get_or_create = ('codigo',)

    programa = factory.SubFactory(ProgramaFactory)
    codigo_acao = '9991'
    codigo = factory.LazyAttribute(lambda o: f'{o.programa.codigo}{o.codigo_acao}')
    nome = 'Manutenção'


class CategoriaApropriacaoFactory(DjangoModelFactory):
    class Meta:
        model = models.CategoriaApropriacao
        django_get_or_create = ('codigo',)

    codigo = '99'
    descricao = 'Categoria de Demonstração'


class GrupoNaturezaDespesaFactory(DjangoModelFactory):
    class Meta:
        model = models.GrupoNaturezaDespesa
        django_get_or_create = ('codigo',)

    codigo = '3'
    nome = 'Outras despesas correntes'


class CategoriaEconomicaDespesaFactory(DjangoModelFactory):
    class Meta:
        model = models.CategoriaEconomicaDespesa
        django_get_or_create = ('codigo',)

    codigo = '3'
    nome = 'Despesas correntes'


class ModalidadeAplicacaoFactory(DjangoModelFactory):
    class Meta:
        model = models.ModalidadeAplicacao
        django_get_or_create = ('codigo',)

    codigo = '90'
    nome = 'Aplicações diretas'


class ElementoDespesaFactory(DjangoModelFactory):
    class Meta:
        model = models.ElementoDespesa
        django_get_or_create = ('codigo',)

    codigo = '30'
    nome = 'Material de consumo'


class NaturezaDespesaFactory(DjangoModelFactory):
    class Meta:
        model = models.NaturezaDespesa
        django_get_or_create = ('categoria_economica_despesa', 'grupo_natureza_despesa', 'modalidade_aplicacao', 'elemento_despesa')

    categoria_economica_despesa = factory.SubFactory(CategoriaEconomicaDespesaFactory)
    grupo_natureza_despesa = factory.SubFactory(GrupoNaturezaDespesaFactory)
    modalidade_aplicacao = factory.SubFactory(ModalidadeAplicacaoFactory)
    elemento_despesa = factory.SubFactory(ElementoDespesaFactory)
    codigo = '339030'
    nome = 'Material de consumo'


class SubElementoNaturezaDespesaFactory(DjangoModelFactory):
    class Meta:
        model = models.SubElementoNaturezaDespesa
        django_get_or_create = ('codigo',)

    natureza_despesa = factory.SubFactory(NaturezaDespesaFactory)
    codigo_subelemento = '99'
    codigo = factory.LazyAttribute(lambda o: f'{o.natureza_despesa.codigo}{o.codigo_subelemento}')
    nome = 'Outros materiais de consumo'
