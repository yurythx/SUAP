from datetime import datetime

from behave import given
from django.apps.registry import apps

from comum.models import Ano
from financeiro.models import CategoriaEconomicaDespesa, ElementoDespesa, GrupoNaturezaDespesa, ModalidadeAplicacao, NaturezaDespesa
from projetos_ensino.models import EixoTematico, TipoBeneficiario

CategoriaBolsa = apps.get_model('ae', 'categoriabolsa')
UnidadeOrganizacional = apps.get_model('rh', 'UnidadeOrganizacional')


@given('os dados básicos para projetos de ensino')
def step_dados_basicos_projetos_ensino(context):
    categoriaeconomicadespesa = CategoriaEconomicaDespesa.objects.get_or_create(codigo='3', nome='Despesas Correntes')[0]
    gruponaturezadespesa = GrupoNaturezaDespesa.objects.get_or_create(codigo='3', nome='Outras Despesas Correntes')[0]
    modalidadeaplicacao = ModalidadeAplicacao.objects.get_or_create(codigo='90', nome='Aplicações Diretas')[0]
    elementodespesa1 = ElementoDespesa.objects.get_or_create(codigo='30', nome='Material de Consumo')[0]
    elementodespesa2 = ElementoDespesa.objects.get_or_create(codigo='18', nome='Auxílio Financeiro a Estudantes')[0]
    elementodespesa3 = ElementoDespesa.objects.get_or_create(codigo='20', nome='Auxílio Financeiro a Pesquisadores')[0]

    NaturezaDespesa.objects.get_or_create(
        categoria_economica_despesa=categoriaeconomicadespesa,
        grupo_natureza_despesa=gruponaturezadespesa,
        modalidade_aplicacao=modalidadeaplicacao,
        elemento_despesa=elementodespesa1,
        codigo='339030',
        nome=elementodespesa1.nome,
    )

    NaturezaDespesa.objects.get_or_create(
        categoria_economica_despesa=categoriaeconomicadespesa,
        grupo_natureza_despesa=gruponaturezadespesa,
        modalidade_aplicacao=modalidadeaplicacao,
        elemento_despesa=elementodespesa2,
        codigo='339018',
        nome=elementodespesa2.nome,
    )

    NaturezaDespesa.objects.get_or_create(
        categoria_economica_despesa=categoriaeconomicadespesa,
        grupo_natureza_despesa=gruponaturezadespesa,
        modalidade_aplicacao=modalidadeaplicacao,
        elemento_despesa=elementodespesa3,
        codigo='339020',
        nome=elementodespesa3.nome,
    )

    if CategoriaBolsa:
        CategoriaBolsa.objects.get_or_create(nome='Bolsa de Extensão', descricao='Bolsa de Extensão', tipo_bolsa='extensão')
        CategoriaBolsa.objects.get_or_create(
            nome='Bolsa de iniciação científica', descricao='Bolsa de iniciação científica', tipo_bolsa='iniciação científica'
        )

    TipoBeneficiario.objects.get_or_create(descricao='Movimentos Sociais')

    Ano.objects.get_or_create(ano=str(datetime.now().year))
    Ano.objects.get_or_create(ano='2018')
    EixoTematico.objects.get_or_create(descricao='Educação')
    EixoTematico.objects.get_or_create(descricao='Cultura')
