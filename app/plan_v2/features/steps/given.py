from behave import given
from hamcrest import assert_that, equal_to

from comum.models import Ano
from financeiro.models import Acao as AcaoFinanceiro
from financeiro.models import (
    AcaoAno,
    CategoriaEconomicaDespesa,
    ElementoDespesa,
    GrupoNaturezaDespesa,
    ModalidadeAplicacao,
    NaturezaDespesa,
    Programa,
)
from plan_v2.models import (
    PDI,
    Acao,
    Dimensao,
    Eixo,
    Indicador,
    Macroprocesso,
    Meta,
    ObjetivoEstrategico,
    PDIAcao,
    PDIMacroprocesso,
    UnidadeAdministrativa,
)
from rh.models import Setor


@given('os dados básicos para o planejamento')
def step_dados_basicos(context):
    """
    Modelos que serão populados:
       > Eixos
       > Dimensões
       > Macroprocessos
       > Ações
    """
    # Recupera dados iniciais necessários
    setor_a1 = Setor.objects.suap_ativos().get(sigla='A1')
    setor_a2 = Setor.objects.suap_ativos().get(sigla='A2')

    # Cadastra os eixos --------------------------------
    eixo1 = None
    if Eixo.objects.filter(nome='Eixo 1').exists():
        eixo1 = Eixo.objects.get(nome='Eixo 1')
    else:
        eixo1 = Eixo(nome='Eixo 1')
        eixo1.save()
    eixo2 = None
    if Eixo.objects.filter(nome='Eixo 2').exists():
        eixo2 = Eixo.objects.get(nome='Eixo 2')
    else:
        eixo2 = Eixo(nome='Eixo 2')
        eixo2.save()
    assert_that(Eixo.objects.all().count(), equal_to(2), 'No cadastro dos eixos')

    # Cadastra as dimensões ----------------------------
    dimensao1 = None
    if Dimensao.objects.filter(codigo='001').exists():
        dimensao1 = Dimensao.objects.get(codigo='001')
    else:
        dimensao1 = Dimensao(codigo='001', nome='Dimensão 1', setor_sistemico=setor_a1, eixo=eixo1)
        dimensao1.save()
    dimensao2 = None
    if Dimensao.objects.filter(codigo='002').exists():
        dimensao2 = Dimensao.objects.get(codigo='002')
    else:
        dimensao2 = Dimensao(codigo='002', nome='Dimensão 2', setor_sistemico=setor_a2, eixo=eixo2)
        dimensao2.save()
    assert_that(Dimensao.objects.all().count(), equal_to(2), 'No cadastro das dimensões')

    # Cadastra de Macroprocessos -----------------------
    macro_1 = None
    if Macroprocesso.objects.filter(nome='Macroprocesso 1').exists():
        macro_1 = Macroprocesso.objects.get(nome='Macroprocesso 1')
    else:
        macro_1 = Macroprocesso(dimensao=dimensao1, nome='Macroprocesso 1', descricao='Descrição do macroprocesso 1')
        macro_1.save()
    macro_2 = None
    if Macroprocesso.objects.filter(nome='Macroprocesso 2').exists():
        macro_1 = Macroprocesso.objects.get(nome='Macroprocesso 2')
    else:
        macro_2 = Macroprocesso(dimensao=dimensao2, nome='Macroprocesso 2', descricao='Descrição do macroprocesso 2')
        macro_2.save()
    assert_that(Macroprocesso.objects.all().count(), equal_to(2), 'No cadastro dos macroprocessos')

    # Cadastro de ações ----------------------------
    acao_1 = None
    if Acao.objects.filter(detalhamento='Ação 1').exists():
        acao_1 = Acao.objects.get(detalhamento='Ação 1')
    else:
        acao_1 = Acao(macroprocesso=macro_1, detalhamento='Ação 1')
        acao_1.save()
    acao_2 = None
    if Acao.objects.filter(detalhamento='Ação 2').exists():
        acao_2 = Acao.objects.get(detalhamento='Ação 2')
    else:
        acao_2 = Acao(macroprocesso=macro_2, detalhamento='Ação 2')
        acao_2.save()
    assert_that(Acao.objects.all().count(), equal_to(2), 'No cadastro das ações')

    # Preenche o modelo dos anos
    for ano in range(2001, 2025):
        Ano.objects.get_or_create(ano=ano)
    ano = Ano.objects.filter(ano='2018')[0]
    Programa.objects.get_or_create(nome='programa 02', codigo='02')
    programa = Programa.objects.get(nome='programa 02')
    # Cria ação no Financeiro
    AcaoFinanceiro.objects.get_or_create(codigo_acao='002', programa=programa, defaults={'codigo': 2, 'nome': 'acao financeira 02'})

    # criar uma AcaoAno no Financeiro
    acaoano = AcaoFinanceiro.objects.get(codigo_acao='002')
    AcaoAno.objects.get_or_create(ano_base=ano, acao=acaoano, valor_capital='100000', valor_custeio='1000000')

    # CategoriaEconomicaDespesa
    cat, _ = CategoriaEconomicaDespesa.get_or_create(codigo='1', nome='categoria 01', descricao='descricao da cat')

    # GrupoNaturezaDespesa
    grupoCat, _ = GrupoNaturezaDespesa.objects.get_or_create(codigo='1', nome='grupo 01', descricao='descricao de grupo')

    # ModalidadeAplicacao
    modalidade, _ = ModalidadeAplicacao.get_or_create(codigo='1', nome='modalidade 01', descricao='modalidade')

    # ElementoDespesa
    elementodespesa, _ = ElementoDespesa.objects.get_or_create(codigo='1', nome='ED 01', descricao='elemento de despesa')

    # NaturezaDespesa
    NaturezaDespesa.get_or_create(
        categoria_economica_despesa=cat,
        grupo_natureza_despesa=grupoCat,
        modalidade_aplicacao=modalidade,
        elemento_despesa=elementodespesa,
        nome='nat de despesa teste',
        codigo='001',
        tipo='Custeio',
    )


@given('os usuários do planejamento')
def step_usuarios_planejamento(context):
    context.execute_steps(
        """
          Dado os seguintes usuários
                 | Nome           | Matrícula | Setor | Lotação | Email             | CPF            | Senha | Grupo                                               |
                 | Administrador  | 109001    | A0    | A0      | pla01@ifrn.edu.br | 000.109.001-10 | abcd  | Administrador de Planejamento Institucional         |
                 | Proreitor_1    | 109002    | A1    | A1      | pla02@ifrn.edu.br | 000.109.002-09 | abcd  | Coordenador de Planejamento Institucional Sistêmico |
                 | Proreitor_2    | 109003    | A2    | A2      | pla03@ifrn.edu.br | 000.109.003-81 | abcd  | Coordenador de Planejamento Institucional Sistêmico |
                 | Coord_campus_1 | 109004    | B1    | B1      | pla04@ifrn.edu.br | 653.710.071-21 | abcd  | Coordenador de Planejamento Institucional           |
                 | Coord_campus_2 | 109005    | B2    | B2      | pla05@ifrn.edu.br | 840.617.325-44 | abcd  | Coordenador de Planejamento Institucional           |
                 | Coord_campus_3 | 109006    | C1    | C1      | pla06@ifrn.edu.br | 222.490.685-42 | abcd  | Coordenador de Planejamento Institucional           |
                 | Coord_campus_4 | 109007    | C2    | C2      | pla07@ifrn.edu.br | 976.731.873-96 | abcd  | Coordenador de Planejamento Institucional           |
    """
    )


@given('um PDI cadastrado')
def step_pdi_cadastrado(context):
    PDI.objects.get_or_create(ano_inicial=Ano.objects.get(ano=2018), ano_final=Ano.objects.get(ano=2022))


@given('as unidades administrativas')
def step_unidades_administrativas(context):
    pdi = PDI.objects.get(ano_inicial__ano=2018, ano_final__ano=2022)

    dados = [
        {'tipo': UnidadeAdministrativa.TIPO_PRO_REITORIA, 'setor': 'A1'},
        {'tipo': UnidadeAdministrativa.TIPO_PRO_REITORIA, 'setor': 'A2'},
        {'tipo': UnidadeAdministrativa.TIPO_CAMPUS, 'setor': 'B1'},
        {'tipo': UnidadeAdministrativa.TIPO_CAMPUS, 'setor': 'B2'},
        {'tipo': UnidadeAdministrativa.TIPO_CAMPUS, 'setor': 'C1'},
        {'tipo': UnidadeAdministrativa.TIPO_CAMPUS, 'setor': 'C2'},
    ]

    for item in dados:
        UnidadeAdministrativa.objects.get_or_create(
            pdi=pdi, tipo=item['tipo'], setor_equivalente=Setor.objects.suap_ativos().get(sigla=item['setor'])
        )


@given('os macroprocessos')
def step_macroprocessos(context):
    pdi = PDI.objects.get(ano_inicial__ano=2018, ano_final__ano=2022)

    PDIMacroprocesso.objects.get_or_create(pdi=pdi, macroprocesso=Macroprocesso.objects.get(nome='Macroprocesso 1'))
    PDIMacroprocesso.objects.get_or_create(pdi=pdi, macroprocesso=Macroprocesso.objects.get(nome='Macroprocesso 2'))


@given('os objetivos estratégicos')
def step_objetivos_estrategicos(context):
    # Adiciona objetivos
    objetivo, _ = ObjetivoEstrategico.objects.get_or_create(
        pdi_macroprocesso=PDIMacroprocesso.objects.get(macroprocesso__nome='Macroprocesso 1'), descricao='Objetivo 1 - Macro 1'
    )

    # Adiciona as metas
    meta, _ = Meta.objects.get_or_create(
        objetivo_estrategico=objetivo, titulo='Objetivo 1 - Meta 1', responsavel=Setor.objects.suap_ativos().get(sigla='A1')
    )

    # Adiciona os indicadores
    Indicador.objects.get_or_create(
        meta=meta,
        denominacao='Indicador 1 - Obj 1 - Meta 1',
        criterio_analise='Indicador 1 - Obj 1 - Meta 1',
        forma_calculo='Forma de cálculo',
        valor_fisico_inicial='0.00',
        valor_fisico_final='100.00',
        metodo_incremento=Indicador.METODO_SOMA,
    )


@given('as ações no PDI')
def step_acoes_pdi(context):
    pdi = PDI.objects.get(ano_inicial__ano=2018, ano_final__ano=2022)
    acao = Acao.objects.get(detalhamento='Ação 1')

    PDIAcao.objects.get_or_create(pdi=pdi, acao=acao)
