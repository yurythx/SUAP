"""Fixtures de fluxo do Planejamento anual.

O planejamento é um pipeline encadeado:

    Configuração -> Dimensão -> Objetivo Estratégico -> Meta
        -> Ação Proposta -> (importar) Ação -> Atividade
        -> Execução / Validação

Cada etapa é montada por ORM como fixture, de modo que cada teste exercita
apenas o endpoint da sua etapa — sem um teste reconstruir o cenário do outro,
como fazia o arquivo legado.
"""

import datetime
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import Group

from comum.models import Ano

# `suap_client` e `sync_permissions` vêm do plugin global (`pytest_plugins` no conftest raiz);
# não as importamos aqui para poder usá-las como parâmetro de fixture.
from comum.pytest_fixtures import api_auth_mocks  # noqa: F401
from djtools.choices import Situacao
from financeiro.models import (
    Acao as AcaoFinanceiro,
)
from financeiro.models import (
    EspecificacaoFonteRecurso,
    FonteRecurso,
    GrupoFonteRecurso,
    Programa,
)
from planejamento.enums import TipoUnidade
from planejamento.models import (
    Acao,
    AcaoProposta,
    Configuracao,
    Dimensao,
    Meta,
    MetaUnidade,
    MetaUnidadeAcaoProposta,
    ObjetivoEstrategico,
    UnidadeAdministrativa,
    UnidadeMedida,
)
from rh.tests.factories import ServidorFactory, SetorFactory

SENHA = '123'

GRUPOS_PLANEJAMENTO = ['Administrador de Planejamento', 'Coordenador de Planejamento Sistêmico', 'Coordenador de Planejamento']


@pytest.fixture
def setor(db):
    """Setor único do cenário: unidade administrativa, dimensão e ação apontam todos para ele."""
    return SetorFactory()


@pytest.fixture
def coordenador(suap_client, sync_permissions, setor):
    """Client autenticado com os perfis de planejamento (sistêmico e de campus)."""
    user = ServidorFactory(setor=setor).get_user()
    for nome in GRUPOS_PLANEJAMENTO:
        user.groups.add(Group.objects.get(name=nome))
    user.set_password(SENHA)
    user.save()
    suap_client.login(username=user.username, password=SENHA)
    return suap_client


@pytest.fixture
def ano():
    return Ano.objects.get_or_create(ano=2012)[0]


@pytest.fixture
def configuracao(ano):
    """Configuração do planejamento anual (define os períodos de cada etapa)."""
    return Configuracao.objects.create(
        ano_base=ano,
        data_geral_inicial=datetime.date(2012, 1, 1),
        data_geral_final=datetime.date(2012, 12, 1),
        data_metas_inicial=datetime.date(2011, 6, 1),
        data_metas_final=datetime.date(2011, 7, 1),
        data_acoes_inicial=datetime.date(2011, 7, 2),
        data_acoes_final=datetime.date(2011, 8, 2),
        data_validacao_inicial=datetime.date(2011, 10, 2),
        data_validacao_final=datetime.date(2011, 12, 2),
        data_planilhas_inicial=datetime.date(2011, 12, 1),
        data_planilhas_final=datetime.date(2011, 12, 20),
    )


@pytest.fixture
def dimensao(setor):
    return Dimensao.objects.create(descricao='Dimensao 01', sigla='SIGLA 01', setor_sistemico=setor, codigo=1)


@pytest.fixture
def objetivo_estrategico(configuracao, dimensao):
    return ObjetivoEstrategico.objects.create(
        macro_projeto_institucional='macro projeto institucional 01',
        descricao='objetivo 01',
        configuracao=configuracao,
        dimensao=dimensao,
        codigo=1,
        data_cadastro=datetime.datetime(2011, 6, 11),
    )


@pytest.fixture
def meta(objetivo_estrategico):
    return Meta.objects.create(
        objetivo_estrategico=objetivo_estrategico,
        titulo='Meta 01',
        justificativa='Meta criada para teste',
        unidade_medida=UnidadeMedida.objects.create(nome='Acesso 01'),
        data_inicial=datetime.date(2012, 1, 1),
        data_final=datetime.date(2012, 12, 1),
        codigo=1,
    )


@pytest.fixture
def recursos():
    """Cadastros do financeiro reaproveitados por ações propostas e ações."""
    programa = Programa.objects.get_or_create(codigo='1', defaults={'nome': 'Programa 01'})[0]
    acao = AcaoFinanceiro.objects.get_or_create(codigo_acao='1', defaults={'nome': 'Fonte 01', 'programa': programa, 'codigo': 1})[0]
    grupo = GrupoFonteRecurso.objects.get_or_create(codigo='1', defaults={'nome': 'grupo recurso 01'})[0]
    especificacao = EspecificacaoFonteRecurso.objects.get_or_create(codigo='01', defaults={'nome': 'especificacao 01'})[0]
    fonte = FonteRecurso.objects.get_or_create(grupo=grupo, especificacao=especificacao, defaults={'codigo': '2', 'nome': 'fonte 01'})[0]
    return SimpleNamespace(programa=programa, acao=acao, grupo=grupo, especificacao=especificacao, fonte=fonte)


@pytest.fixture
def unidade_administrativa(configuracao, setor):
    return UnidadeAdministrativa.objects.create(
        configuracao=configuracao,
        codigo_simec='123456',
        codigo_simec_digito='5',
        setor_equivalente=setor,
        tipo=TipoUnidade.CAMPUS,
        orcamento='20',
    )


@pytest.fixture
def meta_unidade(meta, unidade_administrativa):
    return MetaUnidade.objects.create(meta=meta, unidade=unidade_administrativa, quantidade=10, valor_total='1000')


@pytest.fixture
def acao_proposta(meta, recursos):
    return AcaoProposta.objects.create(
        meta=meta,
        titulo='Acao Proposta 01',
        acao_orcamento=recursos.acao,
        fonte_financiamento=recursos.fonte,
        unidade_medida=UnidadeMedida.objects.create(nome='Acao 01'),
        codigo=2,
        data_inicial=datetime.date(2011, 6, 12),
        data_final=datetime.date(2011, 8, 12),
        data_cadastro=datetime.datetime(2011, 6, 12),
    )


@pytest.fixture
def meta_unidade_acao_proposta(meta_unidade, acao_proposta):
    return MetaUnidadeAcaoProposta.objects.create(meta_unidade=meta_unidade, acao_proposta=acao_proposta, quantidade=10, valor_unitario='10')


@pytest.fixture
def acao(meta_unidade, recursos, setor):
    return Acao.objects.create(
        meta_unidade=meta_unidade,
        titulo='Acao 01',
        detalhamento='acao teste',
        unidade_medida=UnidadeMedida.objects.create(nome='Bolsa'),
        quantidade=5,
        setor_responsavel=setor,
        acao_orcamento=recursos.acao,
        fonte_financiamento=recursos.fonte,
        codigo=1,
        data_inicial=datetime.date(2012, 1, 1),
        data_final=datetime.date(2012, 12, 1),
        status=Situacao.PENDENTE,
    )
