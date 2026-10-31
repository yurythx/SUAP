from behave import given
from django.apps.registry import apps

from financeiro.models import (
    CategoriaEconomicaDespesa,
    ElementoDespesa,
    EspecificacaoFonteRecurso,
    FonteRecurso,
    GrupoFonteRecurso,
    GrupoNaturezaDespesa,
    ModalidadeAplicacao,
    NaturezaDespesa,
)

Ano = apps.get_model('comum', 'Ano')

ProgramaTrabalhoResumido = apps.get_model('financeiro', 'ProgramaTrabalhoResumido')
ProgramaTrabalho = apps.get_model('financeiro', 'ProgramaTrabalho')
ClassificacaoInstitucional = apps.get_model('financeiro', 'ClassificacaoInstitucional')
IdentificadorResultadoPrimario = apps.get_model('financeiro', 'IdentificadorResultadoPrimario')
Funcao = apps.get_model('financeiro', 'Funcao')
Subfuncao = apps.get_model('financeiro', 'Subfuncao')
Acao = apps.get_model('financeiro', 'Acao')
Programa = apps.get_model('financeiro', 'Programa')
Localizacao = apps.get_model('financeiro', 'Localizacao')
EsferaOrcamentaria = apps.get_model('financeiro', 'EsferaOrcamentaria')


@given('os dados básicos para orçamento')
def step_dados_basicos_orcamento(context):
    Ano.objects.get_or_create(ano='2020')[0]
    EsferaOrcamentaria.get_or_create(codigo='1', nome='Orçamento Fiscal')[0]
    classificacao_institucional = ClassificacaoInstitucional.objects.get_or_create(nome='Classificação A', codigo='01')[0]
    ClassificacaoInstitucional.objects.get_or_create(nome='Classificação B', codigo='02')[0]

    resultado_primario = IdentificadorResultadoPrimario.objects.get_or_create(nome='Nome do Resul Primario.', codigo='01')[0]

    funcao = Funcao.objects.get_or_create(nome='Nome da Função', codigo='01')[0]
    subfuncao = Subfuncao.objects.get_or_create(nome='Nome da Subfunção', codigo='01')[0]
    programa = Programa.objects.get_or_create(nome='Nome do Programa', codigo='01')[0]
    acao = Acao.objects.get_or_create(nome='Nome da Ação.', codigo='01', codigo_acao='1111', programa=programa)[0]

    localizacao = Localizacao.objects.get_or_create(nome='Nome da Localização', codigo='01', sigla='RN')[0]
    programa_trabalho = ProgramaTrabalho.objects.get_or_create(funcao=funcao, subfuncao=subfuncao, acao=acao, localizacao=localizacao)[0]
    ProgramaTrabalhoResumido.objects.get_or_create(
        codigo='01',
        classificacao_institucional=classificacao_institucional,
        programa_trabalho=programa_trabalho,
        resultado_primario=resultado_primario,
        tipo_credito='1',
    )

    categoriaeconomicadespesa = CategoriaEconomicaDespesa.objects.get_or_create(codigo='3', nome='Despesas Correntes')[0]
    gruponaturezadespesa = GrupoNaturezaDespesa.objects.get_or_create(codigo='3', nome='Outras Despesas Correntes')[0]
    modalidadeaplicacao = ModalidadeAplicacao.objects.get_or_create(codigo='90', nome='Aplicações Diretas')[0]
    elementodespesa1 = ElementoDespesa.objects.get_or_create(codigo='30', nome='Material de Consumo')[0]

    NaturezaDespesa.objects.get_or_create(
        categoria_economica_despesa=categoriaeconomicadespesa,
        grupo_natureza_despesa=gruponaturezadespesa,
        modalidade_aplicacao=modalidadeaplicacao,
        elemento_despesa=elementodespesa1,
        codigo='339030',
        nome=elementodespesa1.nome,
    )

    especificacao = EspecificacaoFonteRecurso.objects.get_or_create(nome='Especfic do Recurso', codigo='12')[0]
    grupo = GrupoFonteRecurso.objects.get_or_create(nome='Grupo da Fonte do Recurso', codigo='1')[0]
    FonteRecurso.objects.get_or_create(nome='Font do Recurso', codigo='100', grupo=grupo, especificacao=especificacao)[0]
