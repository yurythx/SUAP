from behave import given
from django.apps.registry import apps

from financeiro.models import (
    CategoriaEconomicaDespesa,
    ElementoDespesa,
    GrupoNaturezaDespesa,
    ModalidadeAplicacao,
    NaturezaDespesa,
    SubElementoNaturezaDespesa,
)

MaterialTag = apps.get_model('materiais', 'MaterialTag')
Material = apps.get_model('materiais', 'Material')
Categoria = apps.get_model('materiais', 'Categoria')
UnidadeMedida = apps.get_model('materiais', 'UnidadeMedida')


@given('os dados básicos para materiais')
def step_dados_basicos_materiais(context):
    categoriaeconomicadespesa = CategoriaEconomicaDespesa.objects.get_or_create(codigo='3', nome='Despesas Correntes')[0]
    gruponaturezadespesa = GrupoNaturezaDespesa.objects.get_or_create(codigo='3', nome='Outras Despesas Correntes')[0]
    modalidadeaplicacao = ModalidadeAplicacao.objects.get_or_create(codigo='90', nome='Aplicações Diretas')[0]
    elementodespesa1 = ElementoDespesa.objects.get_or_create(codigo='30', nome='Material de Consumo')[0]

    natureza = NaturezaDespesa.objects.get_or_create(
        categoria_economica_despesa=categoriaeconomicadespesa,
        grupo_natureza_despesa=gruponaturezadespesa,
        modalidade_aplicacao=modalidadeaplicacao,
        elemento_despesa=elementodespesa1,
        codigo='339030',
        nome=elementodespesa1.nome,
    )[0]
    SubElementoNaturezaDespesa.objects.get_or_create(codigo_subelemento='20', nome='Nome do Subelemento', natureza_despesa=natureza, codigo='123')[0]
