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


@given('os dados básicos para compras')
def step_dados_basicos_compras(context):
    MaterialTag.objects.get_or_create(descricao='Permanente')[0]
    tag = MaterialTag.objects.get_or_create(descricao='Informática')[0]
    MaterialTag.objects.get_or_create(descricao='Material esportivo')[0]
    MaterialTag.objects.get_or_create(descricao='Laboratórios')[0]

    categoriaeconomicadespesa = CategoriaEconomicaDespesa.objects.get_or_create(codigo='3', nome='Despesas Correntes')[0]
    gruponaturezadespesa = GrupoNaturezaDespesa.objects.get_or_create(codigo='3', nome='Outras Despesas Correntes')[0]
    modalidadeaplicacao = ModalidadeAplicacao.objects.get_or_create(codigo='90', nome='Aplicações Diretas')[0]
    elementodespesa1 = ElementoDespesa.objects.get_or_create(codigo='31', nome='Compras de Consumo')[0]

    natureza = NaturezaDespesa.objects.get_or_create(
        categoria_economica_despesa=categoriaeconomicadespesa,
        grupo_natureza_despesa=gruponaturezadespesa,
        modalidade_aplicacao=modalidadeaplicacao,
        elemento_despesa=elementodespesa1,
        codigo='339130',
        nome=elementodespesa1.nome,
    )[0]
    subnatureza = SubElementoNaturezaDespesa.objects.get_or_create(
        codigo_subelemento='85', nome='Nome do Subelemento', natureza_despesa=natureza, codigo='123456'
    )[0]
    categoria = Categoria.objects.get_or_create(descricao='Informática', sub_elemento_nd=subnatureza, codigo='1234', codigo_completo='13456')[0]
    unidade = UnidadeMedida.objects.get_or_create(descricao='Gramas')[0]

    material = Material.objects.get_or_create(
        categoria=categoria,
        codigo_catmat='1312313',
        descricao='CABEAMENTO DE TRANSMISSÃO DE DADOS - 33913017.06',
        especificacao='espec',
        unidade_medida=unidade,
    )[0]
    material.tags.add(tag)
