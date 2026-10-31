"""Substrato dos e2e do projetos (Extensão): papéis e um objeto por estado do ciclo de vida.

**Arquitetura (vale para as fatias que estendem esta suíte).** O ciclo do módulo é
edital → projeto → pré-seleção → avaliação → execução → conclusão, e as telas de cada fase só
abrem com o edital na janela certa. Em vez de encadear o estado pela interface entre arquivos
(o que o behave fazia, e amarrava a ordem), cada estado é um **objeto próprio montado direto no
seed** por factories (``projetos/tests/factories.py``):

* ``projetos_seed`` (sessão) devolve ``seed.editais[<estado>]`` e ``seed.projetos[<estado>]``.
  Cada estado tem título fixo (``f'{PREFIXO} <estado>'``) e é **reescrito a cada sessão**: as
  datas são relativas a hoje (``janela``) e os campos de ``EDITAL_BASE``/``PROJETO_BASE`` voltam
  ao valor base, sobrescrito pelo que o estado declara — um ``--reuse-db`` não herda nem data
  vencida nem situação que um teste mexeu. Campo de situação novo entra na BASE, não só no estado.
* **Nova fatia, estado novo**: acrescente uma linha em ``EDITAIS`` / ``PROJETOS`` (e uma fase em
  ``JANELAS``, se for o caso). Não altere um estado existente — algum arquivo já o assume.
* **Estado que o teste consome** (autorizar, classificar, remover, enviar...) nunca é o do seed:
  é fixture de FUNÇÃO que cria objeto novo e o apaga no fim (ver ``edital_novo``), porque a
  suíte não dá flush e as listagens paginadas (``/projetos/editais/``, 20 por página)
  acumulariam lixo a cada execução.
* **Projeto em execução** (fatia 4) é só fixture de função, ``projeto_em_execucao``, sem linha
  em ``PROJETOS``: toda tela da execução grava ou precisa de filhos próprios (metas,
  desembolsos, registros). Vários predicados do model (``is_gerenciador_projeto``,
  ``pode_registrar_execucao``...) leem o usuário da THREAD: no processo do teste ele é ``None``
  — afirme pela tela, nunca chamando esses métodos no corpo do teste.

Decisões deste módulo (seção (c) de ``docs/agents/e2e-receita.md``):

1. **Seed** — factories (#17486): ``semear_base`` (via ``e2e_seed``), o campus CZN e a
   DIAC/CZN com ``campus``/``setor``, os papéis com ``criar_servidores``/``aluno_com_login`` e o
   domínio com as factories do módulo. Não importa ``projetos.features.steps`` (sai com o behave).
2. **Papéis** — sim, eager e na sessão (cache de permissão por processo, armadilha 3). Os
   grupos são os da tabela da feature 001; faixa de matrícula própria, 159xxx.
3. **Relógio** — NÃO congela. As fases do edital são datas relativas a ``datetime.now()``
   (``janela``). Com isso vale o ``storage_states`` (um login por papel na sessão), e não há
   conflito freezegun x django-ninja nem papel de cargo "nascendo hoje" sob data congelada.
4. **Encadeamento** — arquivos independentes, sem prefixo ``NN``; rodam em qualquer ordem.

Rodar (invocação separada da suíte unitária — ver ``djtools/e2e_fixtures.py``)::

    DATABASE_PORT=5433 TEST_DATABASE_NAME=test_suap_projetos_e2e DJANGO_SETTINGS_MODULE=suap.settings_test \\
        uv run pytest projetos/tests/e2e --reuse-db

Gate: ``python bin/scripts/paridade_e2e.py projetos --rotas``.
"""

from __future__ import annotations

import datetime
from collections.abc import Callable, Iterator
from decimal import Decimal
from types import SimpleNamespace
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from playwright.sync_api import expect

# Traz `logado`, `login_ui`, `live_server`, `e2e_seed` e os overrides de `_django_db_helper`/
# `_exige_banco_de_e2e`. Precisa ser star-import em conftest: é a precedência de conftest sobre
# plugin que faz os overrides valerem.
from djtools.e2e_fixtures import *  # noqa: F403
from djtools.e2e_fixtures import aluno_com_login, campus, criar_servidores, setor
from djtools.e2e_ui import Tela

if TYPE_CHECKING:
    from playwright.sync_api import Page

    from ae.models import CategoriaBolsa
    from comum.models import Vinculo
    from edu.models import Aluno, EstruturaCurso
    from financeiro.models import NaturezaDespesa
    from projetos.models import Edital, FocoTecnologico, ItemAvaliacao, Participacao, Projeto, ProjetoAnexo
    from rh.models import Banco, Setor, UnidadeOrganizacional

# Prefixo de tudo que esta suíte cria: âncora dos títulos fixos do seed e da limpeza.
PREFIXO = 'E2E Extensão'

# Apelido -> matrícula (faixa 159xxx, livre no repo). O apelido é o papel, que é metade do que
# cada teste afirma.
PAPEIS = {
    'gerente': '159001',
    'coordenador_extensao': '159002',
    'coordenador_projeto': '159003',
    'avaliador': '159004',
    'aluno': '20191101015901',
    # Fatia 2: coordena o projeto "alheio" das sondas de acesso (servidor sem papel extra).
    'outro_coordenador': '159005',
    # Fatia 3a: quem é indicado pré-avaliador/monitor (já nasce no grupo que a indicação daria) e
    # um segundo avaliador que NUNCA loga — é ele quem perde o grupo nas remoções de indicação.
    'pre_avaliador': '159006',
    'segundo_avaliador': '159007',
    # #17544: lista os projetos de todos os campi no admin, mas só imprime os do próprio.
    'visualizador_campus': '159008',
}

# Matrícula -> (nome, grupos). O gerente fica no campus; os demais na DIAC/CZN (mesma UO).
GERENTES = {'159001': ('Gerente Extensão E2E', ['Gerente Sistêmico de Extensão'])}
SERVIDORES_DIAC = {
    '159002': ('Coordenador Extensão E2E', ['Coordenador de Extensão']),
    '159003': ('Coordenador Projeto E2E', ['Servidor']),
    '159004': ('Avaliador Extensão E2E', ['Servidor', 'Avaliador de Projetos de Extensão']),
    '159005': ('Outro Coordenador E2E', ['Servidor']),
    # Nomes que não contêm "Avaliador Extensão E2E": as listas de indicação casam a linha por `contains`.
    '159006': ('Pré-Avaliadora Sistêmica E2E', ['Servidor', 'Pré-Avaliador Sistêmico de Projetos de Extensão']),
    '159007': ('Segundo Avaliador E2E', ['Servidor', 'Avaliador de Projetos de Extensão']),
    '159008': ('Visualizador Campus E2E', ['Servidor', 'Visualizador de Projetos do Campus']),
}

# Fase do edital -> dias relativos a hoje de (início inscrições, fim inscrições, pré-seleção,
# início seleção, fim seleção, divulgação). Cada tupla põe "agora" dentro da fase que nomeia.
JANELAS = {
    'inscricao': (-1, 5, 10, 15, 20, 21),
    'pre_selecao': (-10, -5, -1, 5, 20, 21),
    'selecao': (-15, -10, -5, -1, 20, 21),
    'resultado_parcial': (-25, -20, -15, -10, -2, 5),
    'divulgado': (-40, -35, -30, -25, -20, -10),
}

# O que todo edital do seed volta a ser a cada sessão, antes dos campos do estado. Literais porque os
# models só são importados dentro das funções: '1' é `Edital.EXTENSAO`/`Edital.CAMPUS`.
EDITAL_BASE = {'tipo_edital': '1', 'tipo_fomento': 'Interno', 'forma_selecao': '1', 'campus_especifico': False, 'autorizado': True, 'publicado': True}

# Estado -> (fase, campos do edital). ``campus_especifico`` no edital em inscrição é o que o
# coordenador de extensão (sem ``pode_gerenciar_edital``) enxerga em "Indicar Avaliador".
EDITAIS = {
    'inscricao': ('inscricao', {'campus_especifico': True}),
    'resultado_parcial': ('resultado_parcial', {}),
    'divulgado': ('divulgado', {}),
    # Mesmo momento, seleção GERAL (`Edital.GERAL`): o resultado agrupa em "Geral", não por campus.
    'divulgado_geral': ('divulgado', {'forma_selecao': '3'}),
    # Fatia 3a: as fases da pré-seleção e da seleção, "de campus" como o de inscrição.
    'pre_selecao': ('pre_selecao', {'campus_especifico': True}),
    'selecao': ('selecao', {'campus_especifico': True}),
}

# Idem para projeto: a situação "em edição" (nada enviado, avaliado nem encerrado).
PROJETO_BASE = {
    'data_conclusao_planejamento': None,
    'pre_aprovado': False,
    'data_pre_avaliacao': None,
    'aprovado': False,
    'data_avaliacao': None,
    'pontuacao': Decimal(0),
    'pontuacao_parcial': Decimal(0),
    'classificacao': None,
    'inativado': False,
    'cancelado': False,
    'concluido': False,
    'data_finalizacao_conclusao': None,
}

# Estado -> (estado do edital, campos de situação do projeto). O coordenador é sempre o
# ``coordenador_projeto``; aprovados levam pontuação para aparecer no resultado e na classificação.
_AVALIADO = {'pre_aprovado': True, 'aprovado': True, 'data_pre_avaliacao': datetime.date.today(), 'data_avaliacao': datetime.date.today()}
PROJETOS = {
    'em_edicao': ('inscricao', {}),
    'aprovado_parcial': ('resultado_parcial', {**_AVALIADO, 'pontuacao': Decimal(8), 'pontuacao_parcial': Decimal(8)}),
    'aprovado_divulgado': ('divulgado', {**_AVALIADO, 'pontuacao': Decimal(9), 'classificacao': 1}),
    'aprovado_divulgado_geral': ('divulgado_geral', {**_AVALIADO, 'pontuacao': Decimal(9), 'classificacao': 1}),
    # Fatia 3a: enviado aguardando a pré-seleção, e pré-selecionado aguardando avaliador.
    'enviado': ('pre_selecao', {'data_conclusao_planejamento': datetime.datetime.now()}),
    'pre_selecionado': (
        'selecao',
        {'data_conclusao_planejamento': datetime.datetime.now(), 'pre_aprovado': True, 'data_pre_avaliacao': datetime.date.today()},
    ),
}

# Gate do modo 2 (`paridade_e2e.py projetos --rotas`): rota -> motivo verificável no código.
ROTAS_DISPENSADAS: dict[str, str] = {}


def janela(fase: str) -> dict[str, datetime.datetime]:
    """As seis datas do edital para que "agora" caia em ``fase`` (ver ``JANELAS``)."""
    agora = datetime.datetime.now()
    campos = ('inicio_inscricoes', 'fim_inscricoes', 'inicio_pre_selecao', 'inicio_selecao', 'fim_selecao', 'divulgacao_selecao')
    return {campo: agora + datetime.timedelta(days=dias) for campo, dias in zip(campos, JANELAS[fase], strict=True)}


# --------------------------------------------------------------------------- substrato


def _papeis() -> Setor:
    """Campus CZN, DIAC/CZN e os papéis; devolve a DIAC/CZN.

    A árvore vem ANTES dos servidores: ``User.VINCULOS`` guarda o setor em cache de classe que
    o ``live_server`` herda (ver ``campus`` em ``djtools/e2e_fixtures.py``).
    """
    czn = campus('CZN', 'Campus Zona Norte')
    diac = setor('DIAC/CZN', czn, 'Diretoria Acadêmica')
    criar_servidores(czn, GERENTES)
    criar_servidores(diac, SERVIDORES_DIAC)
    aluno_com_login(PAPEIS['aluno'], diac, 'Aluno Extensão E2E', 'TECINFO-PROJETOS-E2E')
    return diac


def vinculo(papel: str) -> Vinculo:
    """O ``Vinculo`` do papel — é o que ``Edital``/``Projeto``/``Participacao`` referenciam."""
    from comum.models import User

    return User.objects.get(username=PAPEIS[papel]).get_vinculo()


def clicar_em(tela: Tela, rota: str) -> Tela:
    """Clica no link da tela que aponta para ``rota``: afirma que a UI oferece a ação E a percorre.

    Para as ações que o SUAP renderiza como link (ícones, botões de ``action-bar``, colunas de
    opções do admin). Mais preciso que o texto quando a mesma tela repete o rótulo — a tela do
    edital tem dois "Adicionar Anexo", um por aba. Quem chama declara ``rota`` como literal no
    ``test_*.py``: é esse literal que o gate de rotas enxerga.
    """
    alvo = tela.loc(f'//a[@href="{rota}"]').first
    expect(alvo).to_be_visible()
    alvo.click()
    return tela.esperar()


def _edital(estado: str, uo: UnidadeOrganizacional) -> Edital:
    """O edital do estado, criado uma vez e reposto na janela a cada sessão, com oferta no campus."""
    from projetos.models import Edital, OfertaProjeto
    from projetos.tests.factories import EditalFactory, OfertaProjetoFactory

    fase, campos = EDITAIS[estado]
    titulo = f'{PREFIXO} {estado}'
    edital = Edital.objects.filter(titulo=titulo).first() or EditalFactory(titulo=titulo, cadastrado_por=vinculo('gerente'))
    Edital.objects.filter(pk=edital.pk).update(**janela(fase), **{**EDITAL_BASE, **campos})
    if not OfertaProjeto.objects.filter(edital=edital, uo=uo).exists():
        OfertaProjetoFactory(edital=edital, uo=uo)
    edital.refresh_from_db()
    return edital


def _projeto(estado: str, editais: dict[str, Edital], uo: UnidadeOrganizacional) -> Projeto:
    """O projeto do estado, coordenado pelo ``coordenador_projeto``; a situação é reposta a cada sessão."""
    from projetos.models import Participacao, Projeto
    from projetos.tests.factories import ParticipacaoFactory, ProjetoFactory

    estado_edital, campos = PROJETOS[estado]
    edital = editais[estado_edital]
    titulo = f'{PREFIXO} projeto {estado}'
    projeto = Projeto.objects.filter(edital=edital, titulo=titulo).first() or ProjetoFactory(edital=edital, uo=uo, titulo=titulo)
    if not Participacao.objects.filter(projeto=projeto, responsavel=True).exists():
        # `Participacao.save` com `responsavel` grava o `vinculo_coordenador` do projeto.
        ParticipacaoFactory(projeto=projeto, vinculo_pessoa=vinculo('coordenador_projeto'), responsavel=True)
    Projeto.objects.filter(pk=projeto.pk).update(**{**PROJETO_BASE, **campos})
    projeto.refresh_from_db()
    return projeto


@pytest.fixture(scope='session')
def projetos_seed(e2e_seed) -> SimpleNamespace:
    """Papéis, editais e projetos por estado — idempotente e auto-reparável (ver docstring do módulo)."""
    diac = _papeis()
    editais = {estado: _edital(estado, diac.uo) for estado in EDITAIS}
    projetos = {estado: _projeto(estado, editais, diac.uo) for estado in PROJETOS}
    return SimpleNamespace(uo=diac.uo, editais=editais, projetos=projetos)


@pytest.fixture
def logado_projetos(logado, projetos_seed) -> Callable[[str], Page]:
    """``(papel) -> Page`` autenticada como o papel de ``PAPEIS`` (login cacheado por papel)."""

    def _logado(papel: str) -> Page:
        assert papel in PAPEIS, f'papel desconhecido: {papel}; declare em PAPEIS'
        return logado(PAPEIS[papel])

    return _logado


def _apagar_editais(**filtro: object) -> None:
    """Apaga editais criados por um teste (cascata leva ofertas, anexos e projetos)."""
    from projetos.models import Edital

    for edital in Edital.objects.filter(**filtro):
        edital.delete()


# ---------------------------------------------------------------- fatia 1a: edital


@pytest.fixture
def edital_novo(projetos_seed) -> Iterator[Callable[..., Edital]]:
    """``(**campos) -> Edital`` em inscrição, com oferta no CZN, título único; apagado no fim.

    Para o que o teste consome (autorizar, anexar, remover): o edital do seed é compartilhado.
    """
    from projetos.tests.factories import EditalFactory, OfertaProjetoFactory

    marca = f'{PREFIXO} tmp {uuid4().hex[:8]}'

    def _novo(**campos: object) -> Edital:
        campos.setdefault('cadastrado_por', vinculo('gerente'))
        edital = EditalFactory(titulo=f'{marca} {uuid4().hex[:4]}', **campos)
        OfertaProjetoFactory(edital=edital, uo=projetos_seed.uo)
        return edital

    yield _novo
    _apagar_editais(titulo__startswith=marca)


@pytest.fixture
def editais_da_ui() -> Iterator[list[str]]:
    """Lista onde o teste anota os títulos dos editais que a TELA criou; apagados no fim."""
    titulos: list[str] = []
    yield titulos
    _apagar_editais(titulo__in=titulos)


@pytest.fixture
def edital_para_classificar(edital_novo, projetos_seed) -> Edital:
    """Edital em seleção com dois projetos pré-selecionados avaliados (9 e 7) e UMA vaga no campus.

    A classificação e a aprovação ficam zeradas: é a rotina (o botão "Classificar Projetos") que
    tem de ordená-los e aprovar só o primeiro — ponto de corte = metade da pontuação máxima (10).
    """
    from projetos.models import OfertaProjeto, Projeto
    from projetos.tests.factories import AvaliacaoFactory, CriterioAvaliacaoFactory, ParticipacaoFactory, ProjetoFactory

    edital = edital_novo(**janela('selecao'))
    OfertaProjeto.objects.filter(edital=edital).update(qtd_selecionados=1)
    CriterioAvaliacaoFactory(edital=edital)
    for nota in (7, 9):
        projeto = ProjetoFactory(edital=edital, uo=projetos_seed.uo, titulo=f'{edital.titulo} nota {nota}', pre_aprovado=True)
        ParticipacaoFactory(projeto=projeto, vinculo_pessoa=vinculo('coordenador_projeto'), responsavel=True)
        AvaliacaoFactory(projeto=projeto, vinculo=vinculo('avaliador'), pontuacao=Decimal(nota))
        Projeto.objects.filter(pk=projeto.pk).update(pontuacao=Decimal(nota), classificacao=None, aprovado=False)
    return edital


@pytest.fixture
def anexo_do_membro(projetos_seed) -> Iterator[ProjetoAnexo]:
    """Anexo pendente (sem arquivo) no projeto em edição do seed; apagado no fim."""
    from projetos.tests.factories import ProjetoAnexoFactory

    anexo = ProjetoAnexoFactory(projeto=projetos_seed.projetos['em_edicao'], descricao=f'{PREFIXO} anexo {uuid4().hex[:8]}')
    yield anexo
    anexo.delete()


# ------------------------------------------------- fatia 1b: configuração do edital

# Temas do seed, todos da área "Cultura". Nomes que não são substring um do outro: a tela de
# adicionar tema lista TODOS os temas do banco e ``selecionar_item`` casa a linha por ``contains``.
TEMAS = ('Cultura popular E2E', 'Patrimônio imaterial E2E')


def _despesas() -> None:
    """Naturezas de despesa do autocomplete "Despesa" da fonte de recursos.

    ``financeiro`` não tem ``tests/factories.py`` e criar um só para isto marcaria o app como
    tocado no CI (``SUAP_APPS``). Mesmas chaves e valores do seed do ``pesquisa``
    (``pesquisa/tests/e2e/seed.py``): o job de doc divide banco entre módulos, e o
    ``get_or_create`` precisa casar com o que o outro já gravou.
    """
    from financeiro.models import CategoriaEconomicaDespesa, ElementoDespesa, GrupoNaturezaDespesa, ModalidadeAplicacao, NaturezaDespesa

    categoria = CategoriaEconomicaDespesa.objects.get_or_create(codigo='3', nome='Despesas Correntes')[0]
    grupo = GrupoNaturezaDespesa.objects.get_or_create(codigo='3', nome='Outras Despesas Correntes')[0]
    modalidade = ModalidadeAplicacao.objects.get_or_create(codigo='90', nome='Aplicações Diretas')[0]
    for codigo_elemento, nome_elemento, codigo_natureza in (
        ('30', 'Material de Consumo', '339030'),
        ('18', 'Auxílio Financeiro a Estudantes', '339018'),
    ):
        elemento = ElementoDespesa.objects.get_or_create(codigo=codigo_elemento, nome=nome_elemento)[0]
        NaturezaDespesa.objects.get_or_create(
            categoria_economica_despesa=categoria,
            grupo_natureza_despesa=grupo,
            modalidade_aplicacao=modalidade,
            elemento_despesa=elemento,
            codigo=codigo_natureza,
            defaults={'nome': elemento.nome},
        )


@pytest.fixture(scope='session')
def catalogo_do_edital(projetos_seed) -> SimpleNamespace:
    """Naturezas de despesa e temas: catálogos que a configuração do edital escolhe e ninguém consome."""
    from projetos.tests.factories import TemaFactory

    _despesas()
    return SimpleNamespace(temas=[TemaFactory(descricao=descricao) for descricao in TEMAS])


@pytest.fixture
def edital_de_outro_campus(edital_novo) -> Edital:
    """Edital (seleção por grupo) que o coordenador de extensão do CZN NÃO acessa.

    Fecha as duas portas de ``tem_permissao_acesso_edital`` (``projetos/views.py:859``): sem
    autor (``cadastrado_por``) e com a única oferta na reitoria, não no CZN. Leva uma oferta por
    campus e uma por grupo, que são o alvo das rotas de remoção.
    """
    from rh.models import UnidadeOrganizacional

    from djtools.e2e_fixtures import SIGLA_RAIZ
    from projetos.models import Edital, OfertaProjeto
    from projetos.tests.factories import OfertaProjetoPorGrupoFactory

    edital = edital_novo(cadastrado_por=None, forma_selecao=Edital.GRUPO)
    OfertaProjeto.objects.filter(edital=edital).update(uo=UnidadeOrganizacional.objects.get(sigla=SIGLA_RAIZ))
    OfertaProjetoPorGrupoFactory(edital=edital)
    return edital


@pytest.fixture
def areas_tematicas_do(projetos_seed) -> Iterator[Callable[[str], Vinculo]]:
    """``(papel) -> Vinculo``; ao fim, devolve ao papel as áreas temáticas de interesse que ele tinha.

    ``indicar_areas_tematicas_de_interesse`` tira o vínculo de TODA área não marcada, e a
    indicação de avaliador filtra por área temática: sem restaurar, o teste mudaria quem as
    fatias de avaliação enxergam.
    """
    antes: dict[int, list[int]] = {}

    def _do(papel: str) -> Vinculo:
        alvo = vinculo(papel)
        antes[alvo.pk] = list(alvo.areatematica_set.values_list('pk', flat=True))
        return alvo

    yield _do
    from comum.models import Vinculo as VinculoModel

    for pk, areas in antes.items():
        VinculoModel.objects.get(pk=pk).areatematica_set.set(areas)


# ------------------------------------------------ fatia 2: submissão do projeto

FOCO_TECNOLOGICO = 'Foco tecnológico E2E'


@pytest.fixture(scope='session')
def foco_tecnologico(projetos_seed) -> FocoTecnologico:
    """Foco do CZN. O campo "Foco Tecnológico" do projeto é encadeado ao campus (``campi``): sem ele, a lista vem vazia."""
    from projetos.tests.factories import FocoTecnologicoFactory

    return FocoTecnologicoFactory(descricao=FOCO_TECNOLOGICO, campi=[projetos_seed.uo])


@pytest.fixture
def projeto_novo(edital_novo, projetos_seed, foco_tecnologico, catalogo_do_edital) -> Callable[..., Projeto]:
    """``(coordenador='coordenador_projeto', edital=None, **campos) -> Projeto`` em edição, apagado no fim.

    Cada chamada abre um edital novo em inscrição (``edital_novo``), e o projeto vai com ele na
    cascata do teardown. O projeto sai completo para o ``ProjetoExtensaoForm`` — que a edição
    re-posta inteiro —, com foco, área temática e tema (o edital exige tema por padrão). Esses
    campos NÃO são default da ``ProjetoFactory`` de propósito: a indicação de avaliador filtra
    por área temática, e os projetos do seed não podem ganhar uma.
    """
    from projetos.models import AreaTematica
    from projetos.tests.factories import ParticipacaoFactory, ProjetoFactory

    def _novo(coordenador: str = 'coordenador_projeto', edital: Edital | None = None, **campos: object) -> Projeto:
        edital = edital or edital_novo()
        padrao = {
            'focotecnologico': foco_tecnologico,
            'area_tematica': AreaTematica.objects.get(descricao='Cultura'),
            'tema': catalogo_do_edital.temas[0],
            'fundamentacaoteorica': 'Fundamentação do projeto',
            'referenciasbibliograficas': 'Referências do projeto',
            'atividade_integracao_curricular': False,
            'preve_atividades_internacionalizacao': False,
            'vinculo_coordenador': vinculo(coordenador),
        }
        projeto = ProjetoFactory(edital=edital, uo=projetos_seed.uo, titulo=f'{edital.titulo} projeto', **{**padrao, **campos})
        ParticipacaoFactory(projeto=projeto, vinculo_pessoa=vinculo(coordenador), responsavel=True)
        projeto.refresh_from_db()
        return projeto

    return _novo


@pytest.fixture
def projeto_alheio(projeto_novo) -> SimpleNamespace:
    """Projeto do ``outro_coordenador`` com um filho de cada tipo: o alvo das sondas de acesso.

    O ``coordenador_projeto`` não é membro dele; cada filho (meta, atividade, memória de cálculo,
    desembolso, caracterização, anexo) é o que uma rota "por id do filho" alteraria se a
    checagem de acesso olhasse o projeto errado (#17488).
    """
    from projetos.models import Participacao
    from projetos.tests.factories import (
        CaracterizacaoBeneficiarioFactory,
        DesembolsoFactory,
        EtapaFactory,
        ItemMemoriaCalculoFactory,
        MetaFactory,
        ProjetoAnexoFactory,
    )

    projeto = projeto_novo(coordenador='outro_coordenador')
    participacao = Participacao.objects.get(projeto=projeto, responsavel=True)
    meta = MetaFactory(projeto=projeto)
    item = ItemMemoriaCalculoFactory(projeto=projeto)
    return SimpleNamespace(
        projeto=projeto,
        participacao=participacao,
        meta=meta,
        etapa=EtapaFactory(meta=meta, responsavel=participacao),
        item=item,
        desembolso=DesembolsoFactory(item=item),
        caracterizacao=CaracterizacaoBeneficiarioFactory(projeto=projeto),
        anexo=ProjetoAnexoFactory(projeto=projeto, descricao=f'{PREFIXO} outro anexo'),
    )


# ------------------------------- fatia 3a: pré-seleção e indicação de avaliadores

TEMPORARIOS = f'{PREFIXO} tmp'  # prefixo dos títulos de `edital_novo`


@pytest.fixture
def sem_pre_selecoes(edital_novo) -> Iterator[None]:
    """Apaga as fichas de pré-seleção dos editais temporários ANTES do teardown de ``edital_novo``.

    ``PreSelecao.projeto``, ``ItemPreSelecao.avaliacao`` e ``ItemPreSelecao.criterio`` são
    ``PROTECT``: sem isto, a cascata do edital levanta ``ProtectedError`` e o edital fica no
    banco reusado, empurrando os do seed para fora da página 1 de ``/projetos/editais/``.
    Depender de ``edital_novo`` é o que garante a ordem (teardown em ordem inversa).
    """
    yield
    from projetos.models import ItemPreSelecao, PreSelecao

    ItemPreSelecao.objects.filter(avaliacao__projeto__edital__titulo__startswith=TEMPORARIOS).delete()
    PreSelecao.objects.filter(projeto__edital__titulo__startswith=TEMPORARIOS).delete()


def outra_uo() -> UnidadeOrganizacional:
    """A reitoria: a UO "de outro campus" das sondas — nenhum papel de ``PAPEIS`` é lotado nela."""
    from rh.models import UnidadeOrganizacional

    from djtools.e2e_fixtures import SIGLA_RAIZ

    return UnidadeOrganizacional.objects.get(sigla=SIGLA_RAIZ)


@pytest.fixture
def projeto_enviado_em(edital_novo, projeto_novo, sem_pre_selecoes) -> Callable[..., Projeto]:
    """``(fase, coordenador='coordenador_projeto', uo=None, edital=None, **campos) -> Projeto`` já enviado.

    Cada chamada sem ``edital`` abre um edital novo de campus (``campus_especifico``) na ``fase``
    de ``JANELAS``. ``uo`` põe o projeto em outro campus — e dá ao edital oferta lá, sem a qual
    ``projetos_pre_aprovados`` e a cota de pré-seleção quebram (``ofertaprojeto_set.get(uo=...)``).
    ``campos`` vão para a ``ProjetoFactory`` (``pre_aprovado``, ``aprovado``, ``vinculo_monitor``...).
    O título é o do edital + ``sufixo``: dois projetos no mesmo edital precisam de sufixos que não
    sejam substring um do outro (as filas casam a linha por ``contains``).
    """
    from projetos.models import OfertaProjeto, Projeto
    from projetos.tests.factories import OfertaProjetoFactory

    def _novo(
        fase: str, coordenador: str = 'coordenador_projeto', uo: UnidadeOrganizacional | None = None, sufixo: str = 'projeto', **campos: object
    ) -> Projeto:
        edital = campos.pop('edital', None) or edital_novo(**janela(fase), campus_especifico=True)
        projeto = projeto_novo(coordenador=coordenador, edital=edital, data_conclusao_planejamento=datetime.datetime.now(), **campos)
        mudancas: dict[str, object] = {'titulo': f'{edital.titulo} {sufixo}'}
        if uo is not None:
            if not OfertaProjeto.objects.filter(edital=edital, uo=uo).exists():
                OfertaProjetoFactory(edital=edital, uo=uo)
            mudancas['uo'] = uo
        Projeto.objects.filter(pk=projeto.pk).update(**mudancas)
        projeto.refresh_from_db()
        return projeto

    return _novo


def comissao(edital: Edital, *papeis: str) -> None:
    """Comissão de avaliação do edital com os papéis — ``exige_comissao`` é o default e o caminho do behave (feature 004)."""
    from projetos.tests.factories import ComissaoEditalFactory

    ComissaoEditalFactory(edital=edital, vinculos_membros=[vinculo(papel) for papel in papeis])


@pytest.fixture
def grupos_de(projetos_seed) -> Iterator[Callable[[str], Vinculo]]:
    """``(papel) -> Vinculo``; ao fim, devolve ao usuário do papel os grupos que ele tinha.

    As remoções de indicação tiram o grupo "Avaliador de Projetos de Extensão" de quem fica sem
    indicação. Só use com papel que NÃO loga (``segundo_avaliador``): ``has_group_cached`` guarda
    os grupos em cache local com TTL, e restaurar pelo ORM não chegaria a tempo a quem loga.
    """
    antes: dict[int, list[int]] = {}

    def _de(papel: str) -> Vinculo:
        alvo = vinculo(papel)
        antes[alvo.user.pk] = list(alvo.user.groups.values_list('pk', flat=True))
        return alvo

    yield _de
    from comum.models import User

    for pk, grupos in antes.items():
        User.objects.get(pk=pk).groups.set(grupos)


# ------------------------------------------ fatia 3b: avaliação, recursos e fomento


def avaliacao_de(projeto: Projeto, papel: str, nota: int = 5, **item: object) -> ItemAvaliacao:
    """O ``papel`` indicado (e com o aceite dado) ao projeto e a avaliação dele, com ``nota`` no critério do edital.

    Gravada pela ``AvaliacaoFactory`` (sem ``Avaliacao.save``, que reclassificaria o edital). O
    critério é o primeiro do edital, criado se não houver — SEMPRE amarrado ao edital do
    projeto: a ``SubFactory`` default abriria um edital novo, que o teardown não apaga e que
    empurraria os do seed para fora da página 1 de ``/projetos/editais/``. ``item`` vai para o
    ``ItemAvaliacao`` (``texto_recurso``, ``pontuacao_original``...).
    """
    from projetos.tests.factories import AvaliacaoFactory, AvaliadorIndicadoFactory, CriterioAvaliacaoFactory, ItemAvaliacaoFactory

    criterio = projeto.edital.criterioavaliacao_set.first() or CriterioAvaliacaoFactory(edital=projeto.edital)
    AvaliadorIndicadoFactory(projeto=projeto, vinculo=vinculo(papel), aceito_em=datetime.datetime.now())
    avaliacao = AvaliacaoFactory(projeto=projeto, vinculo=vinculo(papel), pontuacao=Decimal(nota), parecer=f'Parecer de {papel}')
    return ItemAvaliacaoFactory(avaliacao=avaliacao, criterio_avaliacao=criterio, pontuacao=Decimal(nota), **item)


@pytest.fixture
def projeto_avaliado(projeto_enviado_em) -> Callable[..., ItemAvaliacao]:
    """``(fase='resultado_parcial', papel='avaliador', nota=5, **campos) -> ItemAvaliacao`` de um projeto pré-selecionado e avaliado.

    O projeto sai de ``projeto_enviado_em`` (edital novo de campus na ``fase``; ``campos`` vão
    para ele — ``coordenador``, ``uo``, ``edital``, ``sufixo``, situação) já pré-selecionado e
    com ``data_avaliacao``, e o ``papel`` o avaliou (``avaliacao_de``). O edital ganha a data
    limite de recursos 3 dias à frente: em ``resultado_parcial`` (seleção encerrada, resultado
    ainda não divulgado) é a janela em que o coordenador interpõe recurso, o avaliador o julga
    e o gerente reprova manualmente. Tudo que muda nota passa por ``Avaliacao.save``, que
    reclassifica o edital — por isso nunca num edital do seed.
    """
    from projetos.models import Edital

    def _novo(fase: str = 'resultado_parcial', papel: str = 'avaliador', nota: int = 5, **campos: object) -> ItemAvaliacao:
        hoje = datetime.date.today()
        projeto = projeto_enviado_em(fase, **{'pre_aprovado': True, 'data_pre_avaliacao': hoje, 'data_avaliacao': hoje, **campos})
        Edital.objects.filter(pk=projeto.edital_id).update(data_recurso=datetime.datetime.now() + datetime.timedelta(days=3))
        return avaliacao_de(projeto, papel, nota)

    return _novo


# ------------------------------------------------------------ fatia 4: execução do projeto
#
# O projeto em execução NÃO entra em ``PROJETOS``: toda tela desta fase (registrar execução,
# gasto, frequência, prestação de contas...) grava ou precisa de filhos próprios (metas,
# desembolsos, registros), então cada teste pede o seu com ``projeto_em_execucao``. O
# ``aprovado_divulgado`` do seed também está em execução, mas é de leitura das fatias de
# resultado — e sem ``data_conclusao_planejamento`` o formulário de extrato mensal quebra nele.

MATERIAL_PERMANENTE = '449052'  # a única natureza que aceita termo de cessão/doação


def natureza_material_permanente() -> NaturezaDespesa:
    """A natureza 449052 (Equipamentos e Material Permanente), que o catálogo das fatias anteriores não tem.

    ``get_or_create`` pelo código, como ``_despesas``: nada no ``financeiro`` a torna única, e o
    banco é reusado.
    """
    from financeiro.models import CategoriaEconomicaDespesa, ElementoDespesa, GrupoNaturezaDespesa, ModalidadeAplicacao, NaturezaDespesa

    return NaturezaDespesa.objects.get_or_create(
        codigo=MATERIAL_PERMANENTE,
        defaults={
            'nome': 'Equipamentos e Material Permanente',
            'categoria_economica_despesa': CategoriaEconomicaDespesa.objects.get_or_create(codigo='4', nome='Despesas de Capital')[0],
            'grupo_natureza_despesa': GrupoNaturezaDespesa.objects.get_or_create(codigo='4', nome='Investimentos')[0],
            'modalidade_aplicacao': ModalidadeAplicacao.objects.get_or_create(codigo='90', nome='Aplicações Diretas')[0],
            'elemento_despesa': ElementoDespesa.objects.get_or_create(codigo='52', nome='Equipamentos e Material Permanente')[0],
        },
    )[0]


@pytest.fixture
def projeto_em_execucao(projeto_enviado_em) -> Callable[..., SimpleNamespace]:
    """``(coordenador='coordenador_projeto', monitor='coordenador_extensao', uo=None, sufixo='execucao', **campos) -> SimpleNamespace``.

    Projeto aprovado num edital novo já na fase ``divulgado`` — o status "Em execução" sai de
    ``aprovado`` + divulgação passada; sem ``pre_aprovado``/``aprovado`` o ``get_periodo`` o dá
    por encerrado. O ``monitor`` (papel de ``PAPEIS``, ou ``None``) é quem valida a execução; o
    default é o Coordenador de Extensão do campus, que é quem pré-seleciona (armadilha 52).
    Devolve o projeto e um filho de cada tipo que a execução registra: ``participacao`` (a do
    coordenador), ``meta``, ``etapa`` (a atividade), ``item`` (memória de cálculo), ``desembolso``
    e ``caracterizacao``. ``uo``/``edital``/``campos`` seguem para ``projeto_enviado_em``.
    """
    from projetos.models import Participacao
    from projetos.tests.factories import CaracterizacaoBeneficiarioFactory, DesembolsoFactory, EtapaFactory, ItemMemoriaCalculoFactory, MetaFactory

    def _novo(
        coordenador: str = 'coordenador_projeto', monitor: str | None = 'coordenador_extensao', sufixo: str = 'execucao', **campos: object
    ) -> SimpleNamespace:
        hoje = datetime.date.today()
        situacao = {'pre_aprovado': True, 'aprovado': True, 'data_pre_avaliacao': hoje, 'data_avaliacao': hoje}
        situacao['vinculo_monitor'] = vinculo(monitor) if monitor else None
        projeto = projeto_enviado_em('divulgado', coordenador=coordenador, sufixo=sufixo, **{**situacao, **campos})
        participacao = Participacao.objects.get(projeto=projeto, responsavel=True)
        meta = MetaFactory(projeto=projeto)
        item = ItemMemoriaCalculoFactory(projeto=projeto)
        return SimpleNamespace(
            projeto=projeto,
            participacao=participacao,
            meta=meta,
            etapa=EtapaFactory(meta=meta, responsavel=participacao),
            item=item,
            desembolso=DesembolsoFactory(item=item),
            caracterizacao=CaracterizacaoBeneficiarioFactory(projeto=projeto),
        )

    return _novo


# ------------------------------------------------------- fatia 5: equipe e bolsistas
#
# A equipe é FILHA de cada projeto: toda participação desta fatia nasce num projeto descartável
# (``projeto_novo``/``projeto_em_execucao``) e vai embora na cascata dele. A ``ParticipacaoFactory``
# não grava ``HistoricoEquipe``, e é do histórico que certificado, declarações e inativação leem
# as datas: ``membro`` grava os dois, como a tela de adicionar faria.
#
# Participação de ALUNO tem efeito no ``edu``/``ae`` (armadilha 63): ``Participacao.save`` chama
# ``gerencia_bolsa_ae`` (bolsista em projeto aprovado em execução → ``ae.ParticipacaoBolsa``) e,
# para aluno com matriz de extensão, ``AtividadeCurricularExtensao.registrar``. O aluno do seed
# NÃO tem matriz, e as participações dele aqui são de voluntário: nenhum dos dois dispara. Quem
# precisa do caminho de extensão pede ``aluno_de_extensao`` (outro aluno, que não loga).

MATRICULA_ALUNO_EXTENSAO = '20191101015902'


def membro(projeto: Projeto, papel: str, **campos: object) -> Participacao:
    """Participação do ``papel`` na equipe, com a entrada no histórico no início da execução.

    ``campos`` vão para a ``ParticipacaoFactory`` (``vinculo``, ``carga_horaria``, ``ativo``...).
    Quem não é papel de ``PAPEIS`` (aluno de extensão, colaborador externo) entra por
    ``vinculo_pessoa`` em ``campos``; o ``papel`` então só é ignorado.
    """
    from projetos.models import HistoricoEquipe
    from projetos.tests.factories import HistoricoEquipeFactory, ParticipacaoFactory

    campos.setdefault('vinculo_pessoa', vinculo(papel))
    participacao = ParticipacaoFactory(projeto=projeto, **campos)
    if participacao.is_servidor():
        evento = HistoricoEquipe.EVENTO_ADICIONAR_SERVIDOR
    else:
        evento = HistoricoEquipe.EVENTO_ADICIONAR_ALUNO if participacao.eh_aluno() else HistoricoEquipe.EVENTO_ADICIONAR_COLABORADOR
    HistoricoEquipeFactory(participante=participacao, tipo_de_evento=evento)
    return participacao


def banco() -> Banco:
    """Um banco do cadastro de dados bancários (``rh`` não tem factory de ``Banco``; ``get_or_create`` pelo código)."""
    from rh.models import Banco

    return Banco.objects.get_or_create(codigo='001', defaults={'sigla': 'BB', 'nome': 'Banco do Brasil'})[0]


def categoria_bolsa_extensao() -> CategoriaBolsa:
    """A categoria de bolsa de extensão do ``ae`` — ``tipo_bolsa`` é único: ``get_or_create`` por ele, não pelo nome.

    Com ela no banco, ``gerencia_bolsa_ae`` passa a gerar ``ParticipacaoBolsa`` para aluno
    bolsista de projeto aprovado em execução (sem ela, o ``.get`` quebra com 500).
    """
    from ae.models import CategoriaBolsa

    return CategoriaBolsa.objects.get_or_create(tipo_bolsa=CategoriaBolsa.TIPO_EXTENSAO, defaults={'nome': 'Bolsa de Extensão (E2E)'})[0]


@pytest.fixture(scope='session')
def aluno_de_extensao(projetos_seed) -> Aluno:
    """Aluno (que não loga) com matriz de atividades de extensão e uma matrícula-período.

    É o que ``Participacao.is_aluno_extensao`` exige (``matriz__ch_atividades_extensao > 0``) e o
    que ``AtividadeCurricularExtensao.registrar`` precisa (a última matrícula-período). O aluno do
    seed fica sem matriz de propósito: com ela, toda participação dele nas outras fatias passaria
    a gravar no ``edu``. ``edu`` não tem factory de ``Matriz``/``MatriculaPeriodo``: ORM, idempotente.
    """
    from comum.tests.factories import AnoFactory
    from edu.models import Aluno, MatriculaPeriodo, Matriz, SituacaoMatriculaPeriodo
    from edu.tests.factories import SituacaoMatriculaPeriodoFactory

    ano = AnoFactory(ano=datetime.date.today().year)
    cargas = ('obrigatorios', 'optativos', 'eletivos', 'tcc')
    # O crédito da CH no `edu` recalcula os componentes cumpridos do aluno, e isso lê a estrutura
    # do curso (`matriz.estrutura.media_certificacao_conhecimento`): matriz sem estrutura dá 500.
    estrutura = _estrutura_de_curso()
    matriz = Matriz.objects.get_or_create(
        descricao='Matriz com extensão (E2E Extensão)',
        defaults={
            'ano_criacao': ano,
            'data_inicio': datetime.date(ano.ano, 1, 1),
            'qtd_periodos_letivos': 4,
            'ch_seminarios': 0,
            'ch_pratica_profissional': 0,
            'ch_atividades_complementares': 0,
            'ch_atividades_aprofundamento': 0,
            'ch_pratica_como_componente': 0,
            'ch_visita_tecnica': 0,
            'ch_atividades_extensao': 60,
            **{f'ch_componentes_{carga}': 0 for carga in cargas},
        },
    )[0]
    Matriz.objects.filter(pk=matriz.pk).update(estrutura=estrutura)
    aluno = aluno_com_login(MATRICULA_ALUNO_EXTENSAO, setor_da(projetos_seed), 'Aluna Curricularizada E2E', 'TECINFO-PROJETOS-E2E')
    Aluno.objects.filter(pk=aluno.pk).update(matriz=matriz)  # `aluno_com_login` só aplica campos na criação
    MatriculaPeriodo.objects.get_or_create(
        aluno=aluno, ano_letivo=ano, periodo_letivo=1, defaults={'situacao': SituacaoMatriculaPeriodoFactory(id=SituacaoMatriculaPeriodo.MATRICULADO)}
    )
    return Aluno.objects.get(pk=aluno.pk)


def _estrutura_de_curso() -> EstruturaCurso:
    """Estrutura de curso mínima (os valores são os do seed do ``edu``); ``get_or_create`` pela descrição."""
    from edu.models import EstruturaCurso

    return EstruturaCurso.objects.get_or_create(
        descricao='Estrutura com extensão (E2E Extensão)',
        defaults={
            'ativo': True,
            'tipo_avaliacao': EstruturaCurso.TIPO_AVALIACAO_CREDITO,
            'qtd_minima_disciplinas': 1,
            'numero_disciplinas_superior_periodo': 2,
            'qtd_max_periodos_subsequentes': 10,
            'numero_max_cancelamento_disciplina': 1,
            'criterio_avaliacao': EstruturaCurso.CRITERIO_AVALIACAO_NOTA,
            'media_aprovacao_sem_prova_final': 60,
            'media_evitar_reprovacao_direta': 20,
            'media_aprovacao_avaliacao_final': 60,
            'percentual_frequencia': 75,
            'ira': EstruturaCurso.IRA_PONDERADA_POR_CH,
            'qtd_periodos_conclusao': 16,
            'qtd_max_reprovacoes_periodo': 0,
            'qtd_max_reprovacoes_disciplina': 0,
            'qtd_trancamento_voluntario': 2,
            'exige_periodo_ingresso_integralizado': True,
            'percentual_max_aproveitamento': 50,
            'numero_max_certificacoes': 4,
            'media_certificacao_conhecimento': 60,
        },
    )[0]


def setor_da(projetos_seed: SimpleNamespace) -> Setor:
    """A DIAC/CZN — a lotação dos papéis e a diretoria acadêmica do curso dos alunos."""
    from rh.models import Setor

    return Setor.objects.get(sigla='DIAC/CZN', uo=projetos_seed.uo)


@pytest.fixture
def sem_atividades_de_extensao(aluno_de_extensao) -> Iterator[None]:
    """Apaga as ``AtividadeCurricularExtensao`` que as participações do aluno de extensão gravaram no ``edu``.

    A referência é genérica (``tipo_referencia``/``id_referencia``): a cascata do projeto não a
    alcança, e a atividade ficaria no histórico do aluno a cada execução.
    """
    yield
    from edu.models import AtividadeCurricularExtensao

    AtividadeCurricularExtensao.objects.filter(matricula_periodo__aluno=aluno_de_extensao).delete()


@pytest.fixture
def professor_de(projetos_seed) -> Iterator[Callable[[str], None]]:
    """``(papel)``: dá ao papel um ``edu.Professor`` (o que "Adicionar Alunos em Lote" exige); apagado no fim.

    Abrir o assistente grava um ``edu.PeriodoLetivoAtual`` para o usuário
    (``PeriodoLetivoAtual.get_instance``): apagado junto, para o papel não ficar com rastro no ``edu``.
    Nenhum papel de ``PAPEIS`` é professor de verdade: a limpeza é incondicional, e roda também na
    entrada — uma rodada interrompida no ``--reuse-db`` deixaria o ``Professor`` e quebraria a
    premissa "sem professor, 404".
    """
    from edu.models import PeriodoLetivoAtual, Professor

    def _limpar() -> None:
        Professor.objects.filter(vinculo__user__username__in=PAPEIS.values()).delete()
        PeriodoLetivoAtual.objects.filter(user__username__in=PAPEIS.values()).delete()

    def _de(papel: str) -> None:
        Professor.objects.get_or_create(vinculo=vinculo(papel))

    _limpar()
    yield _de
    _limpar()


@pytest.fixture
def email_pessoal_de(projetos_seed) -> Iterator[Callable[[str], str]]:
    """``(papel) -> e-mail``: grava o e-mail pessoal do papel (o duplo fator exige) e devolve o anterior no fim.

    ``User.get_vinculo`` memoriza o vínculo em ``User.VINCULOS`` (dicionário de CLASSE, sem
    invalidação) e o ``live_server`` roda neste mesmo processo: sem tirar o vínculo do cache, a view
    segue lendo a instância antiga, sem o e-mail.
    """
    from comum.models import User
    from comum.models import Vinculo as VinculoModel

    antes: dict[int, tuple[int, str | None]] = {}

    def _gravar(pk: int, usuario: int, email: str | None) -> None:
        VinculoModel.objects.filter(pk=pk).update(email_pessoal=email)
        User.VINCULOS.pop(usuario, None)

    def _de(papel: str) -> str:
        alvo = vinculo(papel)
        antes.setdefault(alvo.pk, (alvo.user_id, alvo.email_pessoal))
        email = f'{PAPEIS[papel]}@pessoal.example'
        _gravar(alvo.pk, alvo.user_id, email)
        return email

    yield _de
    for pk, (usuario, email) in antes.items():
        _gravar(pk, usuario, email)
