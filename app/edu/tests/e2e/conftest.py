"""Substrato dos e2e do edu: relógio congelado em 2019 e seed do módulo.

O edu é o módulo mais encadeado do SUAP: diretoria → curso → turma → matrícula →
período letivo → renovação → formatura. As 13 ``.feature`` do behave modelam essa cadeia
e, para não reconstruí-la a cada cenário, o próprio behave já tem um replay ORM de tudo
em ``edu/tests/e2e/seed.py`` (os steps ``os cadastros da funcionalidade 00N``).
Este conftest reusa esse replay verbatim — mesmo princípio do e2e do almoxarifado, que
reusa ``almoxarifado/features/test_initial_data.py``. A base (catálogos, raiz, ``admin``) é o
seed por factories do ``djtools`` (``semear_base``, #17486); o resto do mundo — anos, árvore
CEN/CZN, servidores — vem de ``seed.semear_estrutura`` e do replay.

Rodar (invocação separada da suíte unitária — ver ``djtools/e2e_fixtures.py``)::

    TEST_DATABASE_NAME=test_suap_e2e DATABASE_PORT=5434 \\
        DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest edu/tests/e2e --reuse-db
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from freezegun import freeze_time

# Traz `logado`, `login_ui`, `live_server`, `e2e_banco` e os overrides de
# `_django_db_helper` (e o `e2e_seed`, que é a base por factories). Precisa ser star-import em conftest: é a precedência de conftest
# sobre plugin que faz os overrides valerem.
from djtools.e2e_fixtures import *  # noqa: F403

# O `Relogio` e o `aquecer_urlconf` foram promovidos ao `djtools` quando o `pesquisa`
# virou o segundo módulo a congelar o relógio. O que fica neste conftest é a decisão do
# módulo: a data base (2019) e os hooks que soltam o relógio ao sair do diretório.
from djtools.e2e_fixtures import SENHA_E2E, Relogio, aquecer_urlconf

# Todo o domínio do edu montado pelo seed vive em 2019 (calendários, turmas, etapas).
DATA_BASE = '10/03/2019'

# Senha dos alunos criados por `seed.cadastrar_aluno`.
SENHA_ALUNO = '123'

# Matrículas dos papéis do seed (feature 001). Nome → matrícula, para os testes não
# ficarem cheios de números mágicos.
PAPEIS = {
    'admin_academico': '100001',
    'secretario': '100002',
    'diretor_geral': '100003',
    'diretor_academico': '100004',
    'coordenador_curso': '100005',
    'registros_academicos': '100006',
    'professor': '100007',
    'operador_enade': '100008',
    'dare': '100009',
    # O discente da cadeia (`MATRICULA_ALUNO_SEED`). Entra aqui para os testes que exercitam
    # o lado do aluno declararem o papel pelo nome, como todos os outros — a senha continua
    # sendo a do aluno (`SENHA_ALUNO`), não a dos servidores.
    'aluno': '20191101010001',
    # Papéis que nenhuma `.feature` usava e que o smoke de rota precisa para não ler 403 de
    # permissão como falha de rota (`seed.SERVIDORES_ROTAS`).
    'migrador': '100010',
    'operador_censo': '100011',
    'admin_edu': '100012',
    'coordenador_napne': '100013',
    'operador_pedemeia': '100014',
    'operador_evento': '100015',
    'professor_grupo': '100016',
    # O discente do smoke NÃO entra aqui: a matrícula dele é sequencial e varia com a execução.
    # Quem precisa dela lê o alvo `matricula_aluno_smoke` (`alvos_rotas.py`).
}


@pytest.fixture(scope='session')
def relogio():
    """Relógio congelado da sessão, iniciado em ``DATA_BASE``.

    Session-scoped de propósito: congelar por teste não serviria. A sessão de login é
    validada contra ``expire_date`` no banco, então um cookie emitido sob uma data e lido
    sob outra é simplesmente uma sessão expirada — o sintoma seria um redirect silencioso
    para ``/accounts/login/``, não um erro de relógio.
    """
    aquecer_urlconf()
    _RELOGIO.congelar(DATA_BASE)
    yield _RELOGIO
    _RELOGIO.descongelar()


# Único por processo: os hooks abaixo precisam alcançar o mesmo relógio que a fixture entrega.
_RELOGIO = Relogio()
_MODULO = Path(__file__).resolve().parents[2]


def pytest_runtest_setup(item: pytest.Item) -> None:
    _RELOGIO.retomar()


def pytest_runtest_teardown(item: pytest.Item, nextitem: pytest.Item | None) -> None:
    """Não deixa 2019 vazar para o próximo módulo.

    O ``relogio`` é de sessão, e o ``pytest -m doc`` do job ``gerar-doc`` roda todos os
    módulos num processo só (``-n 1``): sem isto, quem vem depois do edu roda em 2019 — o
    ``Ano`` corrente do ``avaliacao_integrada`` nasce errado, por exemplo. Estes hooks só
    disparam para itens deste diretório; ``retomar`` restaura a data se o edu voltar a rodar.
    """
    if nextitem is None or not nextitem.path.is_relative_to(_MODULO):
        _RELOGIO.suspender()


def _replay(relogio, *etapas: str) -> None:
    """Executa os steps ``os cadastros da funcionalidade 00N`` do behave, em ordem."""
    from edu.tests.e2e import seed

    for etapa in etapas:
        getattr(seed, f'step_cadastros_feature_{etapa}')(relogio)


MATRICULA_ALUNO_SEED = '20191101010001'


def _normalizar_execucao_anterior() -> None:
    """Desfaz o que uma execução COMPLETA anterior deixa no banco.

    A suíte roda com ``--reuse-db`` e sem flush, e o módulo 11 (``test_fecha_o_periodo_2019_2``)
    fecha o período 2019.2 **à força** — que é o caminho que a ``.feature`` 010 descreve. O
    fechamento forçado tem dois efeitos que nada reverte e que quebram a execução seguinte:

    * a matrícula-período de 2019.2 fica em **Dependência**. ``Aluno.pode_matricula_online``
      exige que a ÚLTIMA matrícula-período esteja em aberto/matriculado/vínculo, então na 2ª
      execução ``/edu/pedido_matricula_seriado/`` recusa e o módulo 07 não renova nada;
    * nasce a matrícula-período do período seguinte (2020.1) em aberto, e ela passa a ser a
      última. ``Aluno.get_urls_documentos`` só oferece "Comprovante de Dados Acadêmicos"
      quando ``not is_ultima_matricula_em_aberto()``, então o documento some no módulo 08.

    O terceiro resíduo é a ``ConfiguracaoPedidoMatricula`` "Renovação 2019.2": o seed 008 a
    recria ao fim de toda execução (a fixture ``renovacao_aberta`` a apaga no teardown, e o
    guard do step a reconstrói depois). Na execução seguinte ela existe quando o módulo 07
    roda, e ``AddCursoConfiguracaoPedidoMatriculaForm.clean`` recusa vincular o mesmo curso a
    uma segunda configuração com datas sobrepostas — o erro aparece dentro do iframe do popup,
    onde o diagnóstico da ``Tela`` não alcança. Apagá-la aqui não muda o fluxo: quem precisa
    dela dentro da execução (``renovacao_aberta`` e o próprio seed 008) a recria.

    Num banco recém-criado nada disto existe e a função é no-op.
    """
    from edu.models import ConfiguracaoPedidoMatricula, MatriculaPeriodo, SituacaoMatriculaPeriodo

    matriculas = MatriculaPeriodo.objects.filter(aluno__matricula=MATRICULA_ALUNO_SEED)
    matriculas.filter(ano_letivo__ano__gt=2019).delete()
    matriculas.filter(ano_letivo__ano=2019, periodo_letivo=2).update(situacao=SituacaoMatriculaPeriodo.MATRICULADO)
    ConfiguracaoPedidoMatricula.objects.filter(descricao='Renovação 2019.2').delete()


@pytest.fixture(scope='session')
def edu_seed(e2e_seed, relogio):
    """Substrato do módulo: replay ORM das funcionalidades 001→004.

    Entrega o mundo até "aluno matriculado em turma": diretoria, curso, matriz,
    componentes, calendário, turma 2019.1 com dois diários configurados e dois alunos.
    Daí para a frente (executar período, encerrar, renovar) quem avança é a **interface**,
    nos módulos ``test_05``→``test_07`` — que é justamente o que se quer cobrir.

    Roda inteiro e antes de qualquer request. Cada ``step_cadastros_feature_00N`` é
    guardado por UMA entidade sentinela (002 por ``TipoComponente`` "POS", 003 por
    ``HorarioCampus`` "Horário Padrão [Aula 45min]", 004 por ``FormaIngresso`` "Ampla
    Concorrência") mas cria muito mais que ela — 003 cria também a turma, os dois diários,
    o professor e os horários de aula. Se um teste de UI criasse a entidade sentinela
    primeiro, o guard curto-circuitaria e o resto do bloco nunca existiria. Por isso os
    testes de **cadastro** (``test_01``→``test_04``) sempre criam objetos com nome único.

    O replay anda com a data internamente; ao final, o relógio volta para ``DATA_BASE``.

    Antes de replicar qualquer coisa, ``_normalizar_execucao_anterior()`` desfaz o estado que
    uma execução completa anterior deixa — é o que torna a suíte re-executável no mesmo banco.
    """
    from edu.tests.e2e import seed

    _normalizar_execucao_anterior()
    seed.semear_estrutura()
    _replay(relogio, '001', '002', '003', '004')
    # Depois do 001 (que cria as diretorias de que estes servidores dependem) e ainda dentro
    # do seed de sessão, antes de qualquer login — o SUAP cacheia grupo por processo. Ver
    # `seed.step_cadastros_servidores_de_rota`.
    seed.step_cadastros_servidores_de_rota(relogio)
    relogio.congelar(DATA_BASE)


@pytest.fixture(scope='session')
def seed_periodo_executado(edu_seed, relogio):
    """Funcionalidade 005: aula, nota e etapa 1 entregue no diário POS.0001.

    Pré-requisito de "encerrar período". Guardado por ``Aula.objects.exists()``, então
    vira no-op quando ``test_05_periodo`` já fez o mesmo pela interface — é por isso que
    aquele módulo usa exatamente os mesmos valores do replay em vez de valores únicos.
    """
    _replay(relogio, '005')
    relogio.congelar(DATA_BASE)


@pytest.fixture(scope='session')
def seed_periodo_fechado(seed_periodo_executado, relogio):
    """Funcionalidade 006: período letivo 2019.1 do aluno fechado e diários fechados."""
    _replay(relogio, '006')
    relogio.congelar(DATA_BASE)


@pytest.fixture(scope='session')
def seed_matricula_renovada(seed_periodo_fechado, relogio):
    """Funcionalidade 008: turmas de 2019.2 geradas e pedido de matrícula processado."""
    _fechar_2019_1()
    _replay(relogio, '008')
    relogio.congelar(DATA_BASE)


@pytest.fixture(scope='session')
def seed_conceito(edu_seed, relogio):
    """Turma, diário e duas alunas no curso "[CONCEITO]" (20202), avaliado por conceito.

    Os dois steps do behave (``as configurações da Avaliação por Conceito`` e ``o cadastro do
    diário com avaliação por conceito``) montam isso; o primeiro só liga
    ``settings.REPRESENTACAO_CONCEITUAL``, que é o que faz o SUAP aceitar A/B/C/D em vez de
    nota. O guard é necessário porque o segundo cria as pessoas com CPF fixo e sem
    ``get_or_create`` — chamá-lo duas vezes estouraria duplicidade de CPF.
    """
    from rh.models import PessoaFisica

    from edu.tests.e2e import seed

    seed.step_configurar_avaliacao_conceito(relogio)
    # O guard é a ALUNA, não a turma: `test_03_turmas` cria turma nesse mesmo curso pelo
    # assistente, e guardar pela turma faria este seed virar no-op — o diário existiria
    # sem ninguém matriculado e o módulo 10 falharia com "sem aluno cursando".
    if not PessoaFisica.objects.filter(cpf='001.001.001-71').exists():
        seed.step_cadastro_turma_diario_conceito(relogio)
    relogio.congelar(DATA_BASE)


def _fechar_2019_1() -> None:
    """Fecha 2019.1 se estiver aberto — é o fechamento que cria a matrícula de 2019.2.

    O replay da funcionalidade 008 precisa da matrícula-período de 2019.2 já existindo (é
    nela que ele faz o pedido de renovação), e essa matrícula nasce do fechamento do período
    anterior. Numa base reusada, ``test_06_encerramento`` pode ter reaberto 2019.1 pela
    interface na execução passada, desfazendo essa progressão — sem este reparo o seed morre
    com ``MatriculaPeriodo matching query does not exist``.
    """
    from edu.models import MatriculaPeriodo, SituacaoMatriculaPeriodo

    abertas = MatriculaPeriodo.objects.filter(
        aluno__curso_campus__codigo='10101', ano_letivo__ano=2019, periodo_letivo=1, situacao=SituacaoMatriculaPeriodo.MATRICULADO
    )
    for matricula_periodo in abertas:
        matricula_periodo.fechar_periodo_letivo(True)


@pytest.fixture(scope='session')
def base_credito(edu_seed, relogio):
    """Pré-cadastros do regime de crédito: área CINE, tipo e componentes "LIC".

    Curso, matriz e estrutura ficam de fora **de propósito**: quem os cria é
    ``test_12_credito``, pela interface, com os nomes da funcionalidade 011 — e é desse curso
    que os módulos 13 (pré/co-requisitos em turma) e 14 (ENADE) dependem, como no behave, em
    que as features 011→013 rodam em sequência sobre o mesmo banco.

    Também apaga o que a execução anterior deixou: os nomes aqui são fixos (o ENADE procura
    "Licenciatura em Geografia") e a suíte e2e não dá flush, então sem esta limpeza a segunda
    execução encontraria curso e matriz já cadastrados e os testes de cadastro falhariam.
    """
    from edu.tests.e2e import seed

    seed.step_cadastro_area_curso_formacao_superior(relogio)
    seed.step_cadastro_tipo_componente(relogio)
    seed.step_cadastro_componente(relogio)
    _criar_calendario_de_duas_etapas()
    _limpar_credito()
    relogio.congelar(DATA_BASE)


CALENDARIO_LICENCIATURA = 'Calendário Acadêmico Licenciatura 2019.2'


def _criar_calendario_de_duas_etapas() -> None:
    """Calendário de 2019.2 com DUAS etapas, para o curso em regime de crédito.

    Os componentes da licenciatura têm duas avaliações (``Qtd. Avaliações = Duas``) e o
    assistente de Gerar Turmas recusa a combinação com o calendário de pós, que tem uma etapa
    só: "A matriz possui componentes com 2 etapas, mas o calendário selecionado possui apenas
    1". O behave tem esse calendário porque as features anteriores o criam pela tela.
    """
    from datetime import date

    from comum.models import Ano
    from edu.models import CalendarioAcademico, Diretoria
    from rh.models import UnidadeOrganizacional

    CalendarioAcademico.objects.get_or_create(
        descricao=CALENDARIO_LICENCIATURA,
        defaults={
            'uo': UnidadeOrganizacional.objects.suap().get(sigla='CEN'),
            'diretoria': Diretoria.objects.get(setor__sigla='DIAC/CEN'),
            'tipo': CalendarioAcademico.TIPO_SEMESTRAL,
            'ano_letivo': Ano.objects.get(ano=2019),
            'periodo_letivo': 2,
            'data_inicio': date(2019, 7, 22),
            'data_fim': date(2019, 12, 29),
            'data_fechamento_periodo': date(2019, 12, 30),
            'qtd_etapas': CalendarioAcademico.QTD_ETAPA_2,
            'data_inicio_etapa_1': date(2019, 7, 22),
            'data_fim_etapa_1': date(2019, 10, 15),
            'data_inicio_etapa_2': date(2019, 10, 16),
            'data_fim_etapa_2': date(2019, 12, 20),
            'data_inicio_prova_final': date(2019, 12, 21),
            'data_fim_prova_final': date(2019, 12, 28),
        },
    )


def _limpar_credito() -> None:
    """Remove a cadeia "Licenciatura em Geografia" da execução anterior, se houver."""
    from edu.models import AreaCurso, ConfiguracaoAtividadeAprofundamento, CursoCampus, EstruturaCurso, Matriz
    from edu.tests.e2e.seed import CODIGO_CURSO_LICENCIATURA, CPF_ALUNA_LICENCIATURA, NOME_CURSO_LICENCIATURA
    from rh.models import PessoaFisica

    # A aluna do regime de crédito é criada com CPF fixo e sem `get_or_create`
    # (``seed.step_matricula_aluno_credito``), então ela tem de sair antes do curso.
    PessoaFisica.objects.filter(cpf=CPF_ALUNA_LICENCIATURA).delete()
    CursoCampus.objects.filter(codigo=CODIGO_CURSO_LICENCIATURA).delete()
    Matriz.objects.filter(descricao=NOME_CURSO_LICENCIATURA).delete()
    EstruturaCurso.objects.filter(descricao='Licenciatura').delete()
    AreaCurso.objects.filter(descricao='Ciências Humanas').delete()
    ConfiguracaoAtividadeAprofundamento.objects.filter(descricao='ATPA Licenciaturas 2018').delete()


@pytest.fixture(scope='session')
def curso_credito(base_credito):
    """``() -> CursoCampus`` do curso em regime de crédito criado por ``test_12_credito``.

    Os módulos 13 e 14 vêm depois de 12 na ordem de coleta (o nome do arquivo é o que
    ordena), então em execução completa o curso já existe. Rodar 13 ou 14 isoladamente falha
    aqui, com esta mensagem — que é melhor que falhar lá dentro por autocomplete vazio.
    """
    from edu.models import CursoCampus

    def _curso():
        curso = CursoCampus.objects.filter(codigo='20101').first()
        assert curso is not None, 'curso "Licenciatura em Geografia" ausente: rode test_12_credito antes (a cadeia 12→13→14 é sequencial)'
        return curso

    return _curso


@pytest.fixture(autouse=True)
def data_do_modulo(request, relogio):
    """Congela a data que o módulo de teste declarar em ``DATA``, ou ``DATA_BASE``.

    O relógio é da sessão (ver ``relogio``), então sem isto a data que um módulo fixou
    vazaria para o próximo — e, pior, para os outros diretórios de e2e coletados depois
    numa run `pytest -m e2e`. Com isto, cada módulo declara a sua e roda isolado.
    """
    relogio.congelar(getattr(request.module, 'DATA', DATA_BASE))
    yield
    # Descongela no fim de CADA teste porque o relógio é da sessão: sem isto, uma run
    # `pytest -m e2e` (a do CI) levaria a data de 2019 para os e2e transversais de
    # `tests/e2e/`, coletados depois e dependentes da data real.
    relogio.descongelar()


@pytest.fixture
def setor_livre(edu_seed):
    """``() -> sigla`` de um setor sem diretoria, seguro para o autocomplete de setor.

    "Seguro" quer dizer duas coisas, aprendidas na marra: o rótulo do autocomplete de setor
    traz também o setor superior, então a sigla escolhida precisa ser de **folha** (senão
    casaria nos rótulos dos filhos) e não pode ser substring da sigla de outro setor. Cada
    chamada devolve uma sigla diferente; ao final, as diretorias criadas sobre elas são
    apagadas — ``Diretoria.setor`` é único e a suíte não dá flush.
    """
    from edu.models import Diretoria
    from rh.models import Setor

    usadas: list[str] = []

    def _proximo() -> str:
        setores = Setor.objects.suap_ativos()
        siglas = sorted(setores.values_list('sigla', flat=True))
        com_filhos = set(setores.filter(superior__isnull=False).values_list('superior__sigla', flat=True))
        ocupadas = set(Diretoria.objects.values_list('setor__sigla', flat=True)) | set(usadas) | com_filhos
        livres = [s for s in siglas if s not in ocupadas and sum(1 for outra in siglas if s in outra) == 1]
        assert livres, 'nenhum setor folha livre para virar diretoria'
        usadas.append(livres[0])
        return livres[0]

    yield _proximo
    Diretoria.objects.filter(setor__sigla__in=usadas).delete()


@pytest.fixture
def grupo_temporario(edu_seed):
    """``(nome_do_grupo) -> queryset`` do vínculo com escopo de setor, desfeito no teardown.

    As telas de vínculo da diretoria gravam ``UsuarioGrupo`` **e** ``UsuarioGrupoSetor``;
    apagar só o segundo deixaria a permissão global de pé e contaminaria os outros módulos
    (o professor sairia daqui podendo gerar turmas). Os testes de vínculo usam sempre o
    professor 100007, que o replay não colocou em nenhum grupo com escopo.
    """
    from django.contrib.auth.models import Group

    from comum.models import UsuarioGrupo, UsuarioGrupoSetor

    nomes: list[str] = []

    def _vinculo(nome_grupo: str, matricula: str = '100007'):
        nomes.append(nome_grupo)
        return UsuarioGrupoSetor.objects.filter(usuario_grupo__group__name=nome_grupo, usuario_grupo__user__username=matricula)

    yield _vinculo
    grupos = Group.objects.filter(name__in=nomes)
    UsuarioGrupoSetor.objects.filter(usuario_grupo__group__in=grupos, usuario_grupo__user__username='100007').delete()
    UsuarioGrupo.objects.filter(group__in=grupos, user__username='100007').delete()


# --- smoke de rota (modo 2 do gate: `bin/scripts/paridade_e2e.py edu --rotas`) ---------------
#
# As rotas de `edu/urls.py` que NÃO viram teste ficam em `ROTAS_DISPENSADAS`, no fim deste
# arquivo, cada uma com o motivo. O gate lê aquele dicionário como literal (AST), por isso
# ele mora aqui e não num módulo importado.


def _pk(modelo, **filtros) -> int:
    """``pk`` determinístico do primeiro registro que casa — ou falha dizendo o que falta.

    ``order_by('id')`` para o smoke não mudar de alvo entre execuções, e `assert` em vez de
    `skip` porque uma rota declarada e não visitada seria cobertura fantasma: o gate lê o
    literal no arquivo, não a request.
    """
    objeto = modelo.objects.filter(**filtros).order_by('id').first()
    assert objeto is not None, f'sem {modelo.__name__} no banco ({filtros}): o smoke de rotas depende do seed da cadeia 01→14'
    return objeto.pk


class _Alvos(dict):
    """``marcador -> valor``, resolvido **na primeira vez que uma rota o usa**.

    Preguiçoso de propósito: resolver todos os alvos de uma vez amarraria cada grupo de rotas
    ao estado de todos os models, e há alvos que só existem depois de um degrau específico do
    seed. Usado com ``str.format_map`` (``format(**mapa)`` copiaria o dicionário e nunca
    chamaria ``__missing__``). O valor fica em cache no próprio dicionário.
    """

    def __init__(self, resolvedores) -> None:
        super().__init__()
        self._resolvedores = resolvedores

    def __missing__(self, marcador: str):
        resolvedor = self._resolvedores.get(marcador)
        assert resolvedor, f'marcador {{{marcador}}} sem alvo declarado em edu/tests/e2e/alvos_rotas.py'
        self[marcador] = resolvedor(_pk)
        return self[marcador]


@pytest.fixture(scope='session')
def seed_de_rotas(edu_seed: None, seed_periodo_executado: None) -> None:
    """Objetos das famílias que a cadeia 01→14 não cria (``edu/tests/e2e/seed_rotas.py``).

    Só o smoke de rota depende disto — nenhum fluxo de ``test_01``→``test_14`` o pede, e é
    assim que se garante que estas linhas novas não mudam o que aqueles testes afirmam.

    Não depende da cadeia ter rodado na mesma invocação: os arquivos de rota rodam sozinhos. O
    ``{aula}`` vem da escada ``seed_periodo_executado``; o aluno do smoke é das fábricas de
    ``seed_rotas`` (por CPF), e licenciatura, ATPA e convocação ENADE também, guardadas por
    existência — na execução completa a tela de ``test_12``→``test_14`` já os criou e elas não
    fazem nada.
    """
    from edu.tests.e2e import seed_rotas

    seed_rotas.montar()


@pytest.fixture(scope='session')
def alvos(edu_seed, seed_de_rotas) -> _Alvos:
    """Alvos dos modelos de URL literais dos ``test_15``→``test_18``.

    As rotas são escritas como ``'/edu/diario/{diario}/'``: o literal continua começando por
    ``/`` e casa o padrão da rota no gate (``<int:pk>`` vira ``[^/]+`` e ``{diario}`` não tem
    barra), e o valor real só entra em tempo de execução. Assim nenhum pk mágico é inventado
    — todo alvo sai do que o seed da cadeia 01→14 já criou.
    """
    from edu.tests.e2e import alvos_rotas

    return _Alvos(alvos_rotas.resolvedores())


@pytest.fixture
def abrir_rotas(logado_edu, alvos):
    """``(papel, rotas) -> None``: abre cada rota como ``papel`` e falha listando as quebradas.

    Um teste por grupo, e não por rota, porque o login é real a cada teste (ver ``logado_edu``):
    parametrizar 600 rotas custaria 600 logins. Em compensação a falha precisa dizer **todas**
    as rotas quebradas de uma vez, senão cada execução revelaria uma só.

    A asserção final compara o que foi de fato requisitado com o que o grupo declara: sem ela,
    um `continue` ou uma exceção engolida deixaria o gate verde sobre rota que ninguém abriu.
    """
    from djtools.e2e_ui import Tela

    def _abrir(papel: str, rotas: tuple, senha: str = SENHA_E2E, arquivo: bool = False) -> None:
        tela = Tela(logado_edu(papel, senha))
        visitadas, falhas = [], []
        for item in rotas:
            modelo, query = item if isinstance(item, tuple) else (item, '')
            url = modelo.format_map(alvos) + (query.format_map(alvos) if query else '')
            visitadas.append(item)
            problema = _abrir_uma(tela, url, arquivo)
            if problema:
                falhas.append(f'{url} -> {problema}')
        assert visitadas == list(rotas), f'rota declarada e não requisitada: {sorted(set(rotas) - set(visitadas), key=str)}'
        assert not falhas, f'como {papel}, {len(falhas)} de {len(rotas)} rotas não abriram:\n  ' + '\n  '.join(falhas)

    return _abrir


def _abrir_uma(tela, url: str, arquivo: bool = False) -> str | None:
    """Abre uma rota e devolve o problema, ou ``None``. Erro de transporte também é problema.

    O ``except`` é largo porque o que se quer aqui é **não perder as outras rotas do grupo**:
    uma exceção do Playwright (timeout, redirect recusado) abortaria o laço e o relatório
    diria "erro interno" em vez de listar as rotas quebradas — que é justamente o que este
    smoke existe para dizer.
    """
    try:
        resposta = tela.buscar(url)
        return _problema_de_arquivo(resposta) if arquivo else _problema(resposta)
    except Exception as erro:
        return f'{type(erro).__name__}: {str(erro).splitlines()[0]}'


# Tipos que as rotas de documento do edu devolvem. `text/html` NÃO está aqui de propósito: é
# exatamente o que o SUAP devolve quando redireciona com mensagem de erro em vez de gerar o
# arquivo, e era isso que a dispensa antiga deixava passar sem ninguém ver.
TIPOS_DE_ARQUIVO = ('application/pdf', 'application/xml', 'text/xml', 'application/vnd.', 'application/octet-stream', 'application/zip')


def _problema_de_arquivo(resposta) -> str | None:
    """Rota que gera arquivo: exige 200, `content-type` de documento e corpo não-vazio.

    "Abriu" não basta para download — o SUAP responde 200 com HTML quando recusa a geração, e
    um smoke que só olha o status chama isso de sucesso.
    """
    problema = _problema(resposta)
    if problema or resposta.status != 200:
        return problema or f'HTTP {resposta.status}'
    tipo = resposta.headers.get('content-type', '')
    if not tipo.startswith(TIPOS_DE_ARQUIVO):
        return f'não devolveu arquivo: content-type {tipo!r}'
    if len(resposta.body()) < 100:
        return f'arquivo vazio ({len(resposta.body())} bytes)'
    return None


def _problema(resposta) -> str | None:
    """O que há de errado com a resposta de uma rota — ou ``None`` se ela abriu.

    ``403`` é falha, não dispensa: significa que o papel declarado no teste está errado, e o
    papel é metade do que o teste afirma. ``404`` idem, para o alvo. O redirect só é aceito
    quando não termina no login: cair no login é sessão inválida, não navegação.
    """
    if resposta.status == 200:
        return None
    if resposta.status in (301, 302):
        destino = resposta.headers.get('location', '')
        return f'redirect para o login ({destino})' if 'login' in destino else None
    return f'HTTP {resposta.status}'


@pytest.fixture
def logado_edu(new_context, login_ui, edu_seed):
    """``(papel) -> Page`` autenticada, com login REAL a cada teste.

    Não usa o ``storage_states`` do ``djtools/e2e_fixtures.py`` (que cacheia um cookie por
    matrícula na sessão inteira) porque os fluxos do edu andam com o relógio: um cookie
    emitido em 10/03/2019 e reusado num teste que congelou 20/07/2019 já está expirado. O
    hasher MD5 de ``suap/settings_test.py`` torna o login por teste barato.
    """

    def _logado(papel: str, senha: str = SENHA_E2E):
        matricula = PAPEIS.get(papel, papel)
        # `base_url` NÃO vai aqui: o `new_context` do pytest-playwright já espalha
        # `browser_context_args`, que o consome da fixture `base_url`.
        contexto = new_context()
        page = contexto.new_page()
        page.on('dialog', lambda dialog: dialog.accept())
        return login_ui(page, matricula, senha)

    return _logado


# --- rotas dispensadas -------------------------------------------------------------------
#
# As rotas de `edu/urls.py` que NÃO viram teste, cada uma com o motivo. Dispensa é para rota
# que não é navegável — nunca para rota que dá trabalho. O gate (`bin/scripts/paridade_e2e.py edu
# --rotas`) lê este dicionário como literal (AST), por isso ele mora aqui e não num módulo
# importado; e `conftest.py` não é varrido em busca de URL, de propósito, para a chave da
# dispensa não contar como rota visitada.
#
# As rotas que renderizam tela mas ainda não têm alvo no seed NÃO estão aqui: elas ficam
# descobertas no gate, e a lista delas é a dívida honesta desta entrega.
ROTAS_DISPENSADAS = {
    # -- Ação de efeito colateral por GET (35)
    '/edu/atender_solicitacao_certificado_enem/<int:pk>/': 'ação de efeito colateral por GET, alcançável só pela listagem; abri-la direto gravaria no banco reusado e corromperia a cadeia 01→14 da execução seguinte',
    '/edu/avaliar_solicitacao_alteracao_resposta/<int:pk>/<int:deferido>/': 'ação de efeito colateral por GET, alcançável só pela listagem; abri-la direto gravaria no banco reusado e corromperia a cadeia 01→14 da execução seguinte',
    '/edu/cancelar_reservas_sala_aula/<int:pk>/': 'ação de efeito colateral por GET, alcançável só pela listagem; abri-la direto gravaria no banco reusado e corromperia a cadeia 01→14 da execução seguinte',
    '/edu/corrigir_inconsistencia_matricula_periodo/<str:matricula>/': 'ação de efeito colateral por GET, alcançável só pela listagem; abri-la direto gravaria no banco reusado e corromperia a cadeia 01→14 da execução seguinte',
    '/edu/corrigir_inconsistencia_periodo/<str:matricula>/': 'ação de efeito colateral por GET, alcançável só pela listagem; abri-la direto gravaria no banco reusado e corromperia a cadeia 01→14 da execução seguinte',
    '/edu/corrigir_inconsistencia_periodo_referencia_periodo_letivo/<int:pk>/': 'ação de efeito colateral por GET, alcançável só pela listagem; abri-la direto gravaria no banco reusado e corromperia a cadeia 01→14 da execução seguinte',
    '/edu/corrigir_inconsistencia_situacao/<int:matricula_periodo_id>/<int:situacao_id>/': 'ação de efeito colateral por GET, alcançável só pela listagem; abri-la direto gravaria no banco reusado e corromperia a cadeia 01→14 da execução seguinte',
    '/edu/delete_componentes_certificacaoparcial_modulo/<int:configuracao_certificacao_parcial_id>/<int:tipo_modulo>/': 'ação de efeito colateral por GET, alcançável só pela listagem; abri-la direto gravaria no banco reusado e corromperia a cadeia 01→14 da execução seguinte',
    '/edu/desarquivar_requerimento/<int:pk>/': 'ação de efeito colateral por GET, alcançável só pela listagem; abri-la direto gravaria no banco reusado e corromperia a cadeia 01→14 da execução seguinte',
    '/edu/importar_aluno/<int:pk>/': 'importa do Q-Acadêmico por DAO (edu/views/procedimentos.py:2203); depende de serviço externo, não de dado local',
    '/edu/remover_coordenador_registro_academico/<int:pk_diretoria>/<int:pk_membro>/': 'ação de efeito colateral por GET, alcançável só pela listagem; abri-la direto gravaria no banco reusado e corromperia a cadeia 01→14 da execução seguinte',
    # -- Alvo de ação em massa (a lista de pks vem da listagem) (24)
    '/edu/aprovar_aluno_turma_minicurso/<str:pks>/': 'alvo de ação em massa: a lista de pks no caminho só existe depois da seleção feita na listagem',
    '/edu/evadir_alunos_selecionados/': 'ação em massa sem pk no caminho: a view lê da requisição a seleção que a listagem monta, e sem ela não há o que processar',
    '/edu/alterar_matriz_alunos_selecionados/': 'ação em massa sem pk no caminho: a view lê da requisição a seleção que a listagem monta, e sem ela não há o que processar',
    '/edu/assinar_diplomas_eletronicos/<str:pk>/': 'alvo de ação em massa: a lista de pks no caminho só existe depois da seleção feita na listagem',
    '/edu/atender_prorrogacao_etapa/<str:pks>/': 'alvo de ação em massa: a lista de pks no caminho só existe depois da seleção feita na listagem',
    '/edu/atender_relancamento_etapa_prorrogando_posse/<str:pks>/': 'alvo de ação em massa: a lista de pks no caminho só existe depois da seleção feita na listagem',
    '/edu/avaliar_equivalencia_componente/<str:pks>/': 'alvo de ação em massa: a lista de pks no caminho só existe depois da seleção feita na listagem',
    '/edu/avaliar_plano_estudo/<str:pks>/': 'alvo de ação em massa: a lista de pks no caminho só existe depois da seleção feita na listagem',
    '/edu/devolver_plano_ensino/<str:destino>/<str:pks>/': 'alvo de ação em massa: a lista de pks no caminho só existe depois da seleção feita na listagem',
    '/edu/dispensar_participacao_enade_em_lote/<int:pk>/<int:curso_campus_pk>/<str:pks>/': 'alvo de ação em massa: a lista de pks no caminho só existe depois da seleção feita na listagem',
    '/edu/emitir_boletim_pdf/<str:pks>/': 'alvo de ação em massa: a lista de pks no caminho só existe depois da seleção feita na listagem',
    '/edu/emitir_historico_final_pdf/<str:pks>/': 'alvo de ação em massa: a lista de pks no caminho só existe depois da seleção feita na listagem',
    '/edu/emitir_historico_parcial_pdf/<str:pk>/': 'alvo de ação em massa: a lista de pks no caminho só existe depois da seleção feita na listagem',
    '/edu/encerrar_suspensao_diarios_lote/<str:pks>/': 'alvo de ação em massa: a lista de pks no caminho só existe depois da seleção feita na listagem',
    '/edu/enviar_certificado_participacao_evento/<int:evento_pk>/<str:pks>/': 'alvo de ação em massa: a lista de pks no caminho só existe depois da seleção feita na listagem',
    '/edu/enviar_certificado_participacao_minicurso/<int:turma_minicurso_pk>/<str:pks>/': 'alvo de ação em massa: a lista de pks no caminho só existe depois da seleção feita na listagem',
    '/edu/imprimir_diploma/<str:pks>/': 'alvo de ação em massa: a lista de pks no caminho só existe depois da seleção feita na listagem',
    '/edu/informar_situacao_registro_auditoria_lote/<int:pk>/<str:situacao>/<str:pks>/': 'alvo de ação em massa: a lista de pks no caminho só existe depois da seleção feita na listagem',
    '/edu/meus_diarios/<str:diarios>/': 'alvo de ação em massa: a lista de pks no caminho só existe depois da seleção feita na listagem',
    '/edu/registrosemissaodiploma_pdf/<str:pks>/': 'alvo de ação em massa: a lista de pks no caminho só existe depois da seleção feita na listagem',
    '/edu/rejeitar_solicitacao/<str:pks>/': 'alvo de ação em massa: a lista de pks no caminho só existe depois da seleção feita na listagem',
    '/edu/reprovar_aluno_turma_minicurso/<str:pks>/': 'alvo de ação em massa: a lista de pks no caminho só existe depois da seleção feita na listagem',
    '/edu/revogar_assinatura_eletronica/<str:pk>/': 'alvo de ação em massa: a lista de pks no caminho só existe depois da seleção feita na listagem',
    '/edu/suspender_diarios_lote/<str:pks>/': 'alvo de ação em massa: a lista de pks no caminho só existe depois da seleção feita na listagem',
    '/edu/transferir_diario/<int:diario_origem>/<str:matriculas_diario>/': 'alvo de ação em massa: a lista de pks no caminho só existe depois da seleção feita na listagem',
    '/edu/transferir_turma/<int:turma_origem>/<str:alunos>/': 'alvo de ação em massa: a lista de pks no caminho só existe depois da seleção feita na listagem',
    # -- Fragmento ajax (17)
    '/edu/cadastrar_pre_requisito_ajax/<int:componente_curricular_pk>/<int:pre_requisito_pk>/': 'fragmento ajax da própria tela (XHR), sem página; o efeito é gravar direto, sem formulário',
    '/edu/dados_atividade_complementar_ajax/<int:aluno_pk>/<int:tipo_pk>/': 'fragmento ajax da própria tela (XHR), sem página; o efeito é gravar direto, sem formulário',
    '/edu/definir_horario_aula_diario_especial_ajax/<int:diario_especial_pk>/<int:horario_aula_pk>/<int:dia_semana_numero>/<str:checked>/': 'fragmento ajax da própria tela (XHR), sem página; o efeito é gravar direto, sem formulário',
    '/edu/definir_horario_coordenador_polo_ajax/<int:horario_funcionamento_pk>/<int:coordenador_polo_pk>/<int:dia_semana_numero>/<str:checked>/': 'fragmento ajax da própria tela (XHR), sem página; o efeito é gravar direto, sem formulário',
    '/edu/definir_horario_polo_ajax/<int:horario_funcionamento_pk>/<int:polo_pk>/<int:dia_semana_numero>/<str:checked>/': 'fragmento ajax da própria tela (XHR), sem página; o efeito é gravar direto, sem formulário',
    '/edu/definir_horario_tutor_polo_ajax/<int:horario_funcionamento_pk>/<int:tutor_polo_pk>/<int:dia_semana_numero>/<str:checked>/': 'fragmento ajax da própria tela (XHR), sem página; o efeito é gravar direto, sem formulário',
    '/edu/listar_atividades_complementares_ajax/<int:aluno_pk>/<int:vinculacao>/': 'fragmento ajax da própria tela (XHR), sem página; o efeito é gravar direto, sem formulário',
    '/edu/napne/profissionais/<int:acolhimento_id>/<int:apoio_id>/<int:uo_id>/json/': 'fragmento ajax da própria tela (XHR), sem página; o efeito é gravar direto, sem formulário',
    '/edu/registrar_chamada_ajax/<int:matricula_diario_pk>/<int:aula_pk>/<int:quantidade>/': 'fragmento ajax da própria tela (XHR), sem página; o efeito é gravar direto, sem formulário',
    '/edu/registrar_conceito_ajax/<int:id_nota_avaliacao>/': 'fragmento ajax da própria tela (XHR), sem página; o efeito é gravar direto, sem formulário',
    '/edu/registrar_conceito_ajax/<int:id_nota_avaliacao>/<str:conceito>/': 'fragmento ajax da própria tela (XHR), sem página; o efeito é gravar direto, sem formulário',
    '/edu/registrar_conceito_final_ajax/<int:id_matricula_diario>/<int:etapa>/': 'fragmento ajax da própria tela (XHR), sem página; o efeito é gravar direto, sem formulário',
    '/edu/registrar_conceito_final_ajax/<int:id_matricula_diario>/<int:etapa>/<str:conceito>/': 'fragmento ajax da própria tela (XHR), sem página; o efeito é gravar direto, sem formulário',
    '/edu/registrar_nota_ajax/<int:id_nota_avaliacao>/': 'fragmento ajax da própria tela (XHR), sem página; o efeito é gravar direto, sem formulário',
    '/edu/registrar_nota_ajax/<int:id_nota_avaliacao>/<int:nota>/': 'fragmento ajax da própria tela (XHR), sem página; o efeito é gravar direto, sem formulário',
    '/edu/remover_pre_requisito_ajax/<int:componente_curricular_pk>/<int:pre_requisito_pk>/': 'fragmento ajax da própria tela (XHR), sem página; o efeito é gravar direto, sem formulário',
    '/edu/vinculacaoatividadeextensao/<int:pk>/avaliar/<str:situacao>/ajax/': 'fragmento ajax da própria tela (XHR), sem página; o efeito é gravar direto, sem formulário',
    # -- Geração de arquivo, sem tela (8)
    # -- Download assinado por token (7)
    '/edu/baixar_pdf_diploma_eletronico/<int:pk>/<str:token>/': 'download assinado por token de uso único; a URL não é navegável fora do link gerado para o interessado',
    '/edu/baixar_xml_historico_escolar/<int:pk>/': 'exige token de download assinado (`AssinaturaDigital.validar_token_download`); sem o link gerado, redireciona com "Token inválido"',
    '/edu/baixar_xml_documentacao_academica/<int:pk>/': 'exige token de download assinado (`AssinaturaDigital.validar_token_download`); sem o link gerado, redireciona com "Token inválido"',
    '/edu/baixar_xml_dados_diploma/<int:pk>/': 'exige token de download assinado (`AssinaturaDigital.validar_token_download`); sem o link gerado, redireciona com "Token inválido"',
    '/edu/baixar_pdf_representacao_visual/<int:pk>/': 'exige token de download assinado (`AssinaturaDigital.validar_token_download`); sem o link gerado, redireciona com "Token inválido"',
    '/edu/baixar_pdf_representacao_visual/<int:pk>/<str:token>/': 'download assinado por token de uso único; a URL não é navegável fora do link gerado para o interessado',
    '/edu/baixar_xml_dados_diploma/<int:pk>/<str:token>/': 'download assinado por token de uso único; a URL não é navegável fora do link gerado para o interessado',
    '/edu/baixar_xml_documentacao_academica/<int:pk>/<str:token>/': 'download assinado por token de uso único; a URL não é navegável fora do link gerado para o interessado',
    '/edu/baixar_xml_historico_escolar/<int:pk>/<str:token>/': 'download assinado por token de uso único; a URL não é navegável fora do link gerado para o interessado',
    '/edu/baixar_xml_historico_escolar_parcial/<int:pk>/<str:token>/': 'download assinado por token de uso único; a URL não é navegável fora do link gerado para o interessado',
    '/edu/imprimir_certificado_participacao_evento/<str:token>/': 'download assinado por token de uso único; a URL não é navegável fora do link gerado para o interessado',
    # -- Endpoint sem tela (2)
    '/edu/imprimir_certificado_participacao_evento/<int:pk>/': 'o certificado exige modelo cadastrado no evento; sem ele a view captura a exceção e redireciona com mensagem, sem gerar arquivo',
    '/edu/participanteturmaminicurso/<int:pk>/vincular_atividadepraticaprofissional/<int:aluno_id>/': 'vínculo por GET a partir da listagem de participantes; a view devolve 500 sem a atividade de prática já associada ao participante',
    '/edu/finalizar_sessao_assinatura_eletronica/': 'encerra sessão de assinatura aberta pelo próprio fluxo de assinatura; fora dele a permissão do assinante não existe',
    '/edu/remover_auxiliar_secretaria/<int:pk>/<int:usuario_grupo_pk>/': 'remoção a partir da aba da diretoria: o `UsuarioGrupo` tem de estar no escopo da diretoria, estado que só a própria tela de vínculo monta',
    '/edu/remover_estagiario_secretaria/<int:pk>/<int:usuario_grupo_pk>/': 'remoção a partir da aba da diretoria: o `UsuarioGrupo` tem de estar no escopo da diretoria, estado que só a própria tela de vínculo monta',
    '/edu/alunos_ws/': 'webservice do EAD, não tela: autoriza por IP de máquina cadastrada em ponto.Maquina e devolve dado serializado',
}
