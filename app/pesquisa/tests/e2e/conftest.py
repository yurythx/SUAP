"""Substrato dos e2e do pesquisa (modo 2): relógio congelado em 2018, papéis e o seed da cadeia.

O PESQUISA é o maior módulo do repo em cenários de behave (86 ativos em 16 arquivos) e a
metade PESQUISA deles — os cenários 001 a 011 — é uma **cadeia**: o edital da 001 é o edital que
a 002 submete projeto, que a 003 pré-avalia, que a 004 distribui entre avaliadores, que a 005
avalia, que a 006 distribui bolsas, que a 007 executa, que a 008 monitora, que a 009 conclui,
que a 010 finaliza e que a 011 valida. Nenhuma delas monta o próprio mundo do zero, e o
behave conta com isso: os cenários compartilham banco, e a ordem do arquivo é a ordem do
fluxo. Daí três consequências de infra, todas já pagas em ``edu/tests/e2e/conftest.py``:

1. **Relógio congelado de SESSÃO.** As features fixavam a data com
   ``Quando a data do sistema for "dd/mm/aaaa"`` e o edital da 001 tem períodos em janeiro de
   2018 (inscrições 01→10/01, pré-seleção 11/01, seleção 15→17/01, divulgação 19/01). Cada
   feature roda numa data diferente dessa janela, e a cadeia só fecha se elas vierem na
   ordem. Congelar por teste não serve: a sessão de login é validada contra ``expire_date``
   no banco, então cookie emitido numa data e lido noutra é sessão expirada — o sintoma
   seria um redirect silencioso para ``/accounts/login/``, não um erro de relógio.

2. **Login real a cada teste**, sem o ``storage_states`` do ``djtools/e2e_fixtures.py``
   (que cacheia um cookie por matrícula na sessão inteira) pela mesma razão: o cookie
   expiraria ao trocar a data. O hasher MD5 de ``suap/settings_test.py`` torna isso barato.

3. **Papéis criados ANTES da primeira request.** O SUAP resolve permissão com cache por
   processo: um vínculo de grupo criado no meio da sessão deixa a tela que já respondeu 403
   respondendo 403 para sempre.

Rodar (invocação separada da suíte unitária — ver ``djtools/e2e_fixtures.py``)::

    TEST_DATABASE_NAME=test_suap_pesquisa_e2e DJANGO_SETTINGS_MODULE=suap.settings_test \\
        uv run pytest pesquisa/tests/e2e -m e2e --reuse-db

Os arquivos são **numerados** (``test_01_edital.py`` → ``test_11_...``) porque a cadeia é
sequencial e o nome é o que ordena a coleta: rodar ``test_05`` sozinho falha por falta do
projeto que ``test_02`` submeteu, e isso é de propósito — é a mesma relação que as ``.feature``
têm entre si.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

# Traz `logado`, `login_ui`, `live_server`, `e2e_seed` e os overrides de
# `_django_db_helper`. Precisa ser star-import em conftest: é a precedência de conftest
# sobre plugin que faz os overrides valerem.
from djtools.e2e_fixtures import *  # noqa: F403
from djtools.e2e_fixtures import Relogio, aquecer_urlconf
from pesquisa.tests.e2e.seed import MATRICULA_PARECERISTA

# Data da sessão: é quando o substrato (``seed.py``) é montado. Não é uma data "neutra" —
# ``datetime.now()`` aparece no próprio seed (``Ano`` do aluno, ``Entrada`` do laboratório) e
# tem de cair dentro de 2018 para casar com o ``Ano`` que a feature 002 escolhe no
# desembolso e com o ano letivo que o aluno recebe.
DATA_BASE = '01/01/2018'

MODULO = Path(__file__).resolve().parents[2]

# Matrícula → apelido, para os testes não ficarem cheios de números mágicos. Os nomes são os
# papéis da tabela da feature 001, não os nomes próprios: é o papel que metade do teste afirma.
PAPEIS = {
    'diretor': '108001',
    'coordenador_pesquisa': '108002',
    'coordenador_pesquisa_outro_campus': '108090',
    'coordenador_projeto': '108003',
    'servidor_projeto': '108004',
    'avaliador_1': '108005',
    'avaliador_2': '108006',
    'aluno': '20191101011081',
    'coordenador_laboratorio': '108013',
    'membro_laboratorio': '108014',
    # Papéis da editora (tabela da feature 012). O fluxo editorial da 014 é uma esteira, e
    # cada etapa é de um grupo — por isso o apelido diz a etapa, não o nome próprio.
    'integrante_editora': '108007',
    'conselheiro': '108008',
    'revisor': '108009',
    'diagramador': '108010',
    'bibliotecario': '108011',
    'autor_obra': '108012',
    # Prestador de serviço do módulo (``seed.criar_parecerista``), quem avalia obra na feature 014.
    'parecerista_obra': MATRICULA_PARECERISTA,
}


# Único por processo: os hooks abaixo precisam alcançar o MESMO relógio que a fixture entrega.
# A classe vem do `djtools` (promovida quando este módulo virou o segundo a congelar o
# relógio, depois do `edu`); o que fica aqui é a decisão do módulo — a data base e os hooks.
_RELOGIO = Relogio()


@pytest.fixture(scope='session')
def relogio():
    """Relógio congelado da sessão, iniciado em ``DATA_BASE``."""
    aquecer_urlconf()
    _RELOGIO.congelar(DATA_BASE)
    yield _RELOGIO
    _RELOGIO.descongelar()


def pytest_runtest_setup(item: pytest.Item) -> None:
    _RELOGIO.retomar()


def pytest_runtest_teardown(item: pytest.Item, nextitem: pytest.Item | None) -> None:
    """Não deixa janeiro de 2018 vazar para o próximo módulo.

    O ``relogio`` é de sessão e o ``pytest -m e2e`` do CI roda todos os diretórios num
    processo só: sem isto, os e2e transversais de ``tests/e2e/`` — coletados depois e
    dependentes da data real — rodariam em 2018. Os hooks só disparam para itens deste
    diretório; ``retomar`` restaura a data se o pesquisa voltar a rodar.
    """
    if nextitem is None or not nextitem.path.is_relative_to(MODULO):
        _RELOGIO.suspender()


@pytest.fixture(autouse=True)
def data_do_modulo(request, relogio):
    """Congela a data que o módulo declarar em ``DATA``, ou ``DATA_BASE``.

    É o análogo pytest do ``Quando a data do sistema for`` de cada cenário: cada arquivo
    declara a data em que a feature dele roda, e a cadeia funciona porque essas datas estão em
    ordem crescente dentro da janela do edital.
    """
    relogio.congelar(getattr(request.module, 'DATA', DATA_BASE))
    yield
    # Descongela no fim de CADA teste: o relógio é da sessão, e uma run `pytest -m e2e` levaria
    # 2018 para os módulos coletados depois.
    relogio.descongelar()


@pytest.fixture(scope='session')
def pesquisa_seed(e2e_seed, relogio):
    """O substrato do módulo: cadastros básicos, os 9 papéis da tabela e o Lattes deles.

    Vem do replay dos passos do behave (``pesquisa/features/steps/given.py``, aposentado com o
    resto do behave do módulo), com a árvore e os atores criados por factories (ver
    ``pesquisa/tests/e2e/seed.py``), do mesmo jeito que o ``edu`` reusa
    ``edu/tests/e2e/seed.py``.

    Session-scoped e antes de qualquer request, primeiro pelo cache de permissão por processo
    e depois porque os passos que ele transcreve usam ``objects.get()``: o coordenador tem de
    existir antes de ganhar currículo Lattes.
    """
    from pesquisa.tests.e2e import seed

    seed.montar()
    relogio.congelar(DATA_BASE)


@pytest.fixture(scope='session')
def papeis(pesquisa_seed) -> dict:
    """``matrícula -> User`` de todos os atores das tabelas da feature 001 e da 012.

    A chave é ``User`` e não ``Servidor``/``Aluno`` porque o elenco do módulo não é homogêneo:
    servidores, um aluno e um **prestador de serviço** (o parecerista de obra da feature 014,
    que não é nem um nem outro). ``User`` é o único denominador comum e é o que o login usa.

    Serve para ``logado_pesquisa`` recusar papel digitado errado antes de tentar logar — o
    sintoma sem isso seria um ``DoesNotExist`` no meio de um teste, que parece defeito do teste.
    """
    return {matricula: _objeto(matricula) for matricula in PAPEIS.values()}


def _objeto(matricula: str):
    """O ``User`` daquela matrícula, seja servidor, aluno ou prestador de serviço.

    ``comum.User`` e não ``django.contrib.auth.models.User``: o SUAP troca o modelo de usuário
    (``AUTH_USER_MODEL``), e o ``auth.User`` está *swapped* — importar do ``auth`` levanta
    ``Manager isn't available; 'auth.User' has been swapped for 'comum.User'``.
    """
    from comum.models import User

    usuario = User.objects.filter(username=matricula).first()
    assert usuario is not None, f'não há usuário {matricula!r}: confira o seed (``seed.montar_papeis``)'
    return usuario


@pytest.fixture
def projeto_em_execucao(projeto_do_fluxo) -> Iterator[object]:
    """Reabre, só durante um teste, o projeto da cadeia para solicitar serviço de laboratório.

    A feature 015 roda depois da validação final da 011, mas a tela só oferece "Solicitar
    Serviço" a coordenadores com projeto aprovado cuja conclusão ainda não foi avaliada. O
    registro é restaurado no teardown para não reabrir o projeto para a feature 016 nem para o
    smoke de rotas. O escopo de função evita compartilhar esse estado consumível.
    """
    projeto = projeto_do_fluxo()
    registro = projeto.registroconclusaoprojeto_set.order_by('id').first()
    assert registro is not None, 'a feature 009 deveria ter criado o registro de conclusão antes da 015'
    dt_avaliacao = registro.dt_avaliacao
    registro.dt_avaliacao = None
    registro.save(update_fields=['dt_avaliacao'])
    yield projeto
    registro.dt_avaliacao = dt_avaliacao
    registro.save(update_fields=['dt_avaliacao'])


@pytest.fixture
def logado_pesquisa(new_context, login_ui, papeis):
    """``(papel) -> Page`` autenticada, com login REAL a cada teste.

    ``papel`` é o apelido de ``PAPEIS`` (``'diretor'``) ou a própria matrícula; ambos passam,
    porque há teste que exercita um ator que não merece apelido.
    """

    def _logado(papel: str, senha: str | None = None):
        matricula = PAPEIS.get(papel, papel)
        assert matricula in papeis, f'papel desconhecido: {papel!r}; declare em PAPEIS'
        # `base_url` NÃO vai aqui: o `new_context` do pytest-playwright já espalha
        # `browser_context_args`, que o consome da fixture `base_url`.
        contexto = new_context()
        page = contexto.new_page()
        page.on('dialog', lambda dialog: dialog.accept())
        return login_ui(page, matricula, senha)

    return _logado


# --- âncoras de domínio ------------------------------------------------------------------
#
# A cadeia é longa e cada arquivo precisa do objeto que o anterior produziu. Estas âncoras
# resolvem os objetos por chave natural (título) em vez de por pk chumbado, que mudaria de
# execução para execução.


def _ancora(modelo, titulo: str, campo: str, origem: str):
    """Primeiro objeto com aquele título — ou falha dizendo quem o cria.

    O ``assert`` com o arquivo de origem é deliberado: rodar ``test_05`` sozinho tem de dizer
    "a cadeia é sequencial, comece pelo test_01", não estourar um ``DoesNotExist`` do Django
    dentro do teste, que parece defeito do teste.
    """
    objeto = modelo.objects.filter(**{campo: titulo}).order_by('id').first()
    assert objeto is not None, (
        f'{modelo.__name__} {titulo!r} ausente: a cadeia é sequencial, rode `pytest pesquisa/tests/e2e` inteiro (quem cria é {origem})'
    )
    return objeto


@pytest.fixture
def edital_do_fluxo():
    """``(titulo='Nome do edital') -> Edital`` criado pela feature 001."""
    from pesquisa.models import Edital

    return lambda titulo='Nome do edital': _ancora(Edital, titulo, 'titulo', 'test_01_edital.py')


@pytest.fixture
def projeto_do_fluxo():
    """``(titulo='Título do projeto') -> Projeto`` submetido pela feature 002."""
    from pesquisa.models import Projeto

    return lambda titulo='Título do projeto': _ancora(Projeto, titulo, 'titulo', 'test_02_projeto.py')


def mover_inicio_das_inscricoes(edital, *, inicio: str, fim: str) -> None:
    """Move a janela de inscrições do edital e a restaura no fim do teste.

    A cadeia roda DENTRO da janela do edital — é o que faz cada feature funcionar. Então o
    único jeito honesto de exercitar a recusa por prazo é mover o prazo, nunca o relógio: o
    relógio é da sessão e mexer nele invalidaria a sessão de login (ver a docstring do
    módulo).

    Devolve as datas originais para o chamador restaurar; não restaura sozinho porque o teste
    pode querer afirmar a recusa antes de restaurar.
    """
    from datetime import datetime

    original = (edital.inicio_inscricoes, edital.fim_inscricoes)
    edital.inicio_inscricoes = datetime.strptime(f'{inicio} 00:00', '%d/%m/%Y %H:%M')
    edital.fim_inscricoes = datetime.strptime(f'{fim} 00:00', '%d/%m/%Y %H:%M')
    edital.save()
    return original


__all__ = ['PAPEIS', 'mover_inicio_das_inscricoes']


@pytest.fixture
def em_data(relogio):
    """``(dd/mm/aaaa) -> None``: move o relógio da sessão para a data daquele passo.

    Existe porque na feature 014 **cada cenário roda numa data diferente** (a esteira editorial
    dura janeiro e fevereiro de 2018, e o edital da 012 tem uma janela por etapa), enquanto o
    ``data_do_modulo`` congela uma data por ARQUIVO. Em vez de um arquivo por cenário — que
    perderia a ordem da esteira, já que a coleta do pytest não a garante entre arquivos — o
    arquivo declara ``DATA`` só como piso e cada teste avança o relógio para a sua data.

    O relógio é o da sessão de propósito (ver a docstring do módulo): mover o relógio entre
    testes invalida a sessão de browser, e é por isso que cada teste já loga de novo.
    """

    def _em_data(data_br: str) -> None:
        relogio.congelar(data_br)

    return _em_data


# Fixtures do smoke de rotas (`test_17_rotas.py` e `test_18_rotas_editora_pi.py`).
@pytest.fixture(scope='session')
def alvos(pesquisa_seed):
    """Alvos das rotas com parâmetro, resolvidos a partir do que a cadeia criou."""
    from pesquisa.tests.e2e import alvos_rotas

    return alvos_rotas.Alvos(alvos_rotas.resolvedores())


@pytest.fixture
def guardadas():
    """Acumula as rotas que responderam 403, para o relatório de fim de execução."""
    return []


@pytest.fixture
def abrir_rotas(logado_pesquisa, alvos, guardadas):
    """`(papel, rotas) -> None`: abre cada rota como `papel` e falha listando as quebradas."""

    def _abrir_todas(papel, rotas, alvos=None):
        from pesquisa.tests.e2e.alvos_rotas import abrir

        falhas, sem_acesso = abrir(logado_pesquisa(papel), rotas, papel, alvos)
        guardadas.extend(sem_acesso)
        assert not falhas, f'como {papel}, {len(falhas)} de {len(rotas)} rotas não abriram:\n  ' + '\n  '.join(falhas)

    return _abrir_todas


# --- rotas dispensadas (o gate `paridade_e2e.py pesquisa --rotas`) ----------------------
#
# Toda rota de `pesquisa/urls.py` que **não** é aberta pelo smoke (`test_17_rotas.py`) está
# aqui, com o motivo. As que o smoke abre estão declaradas lá como literal, e é isso que o
# gate lê.
#
# O motivo é específico por rota — a view e a linha, e o que a impede — porque é lido por
# humano na revisão: "difícil" não é motivo, e uma dispensa genérica transformaria o gate num
# carimbo. O módulo tem 343 rotas e 338 views distintas: quase tudo é endpoint de ação, não
# tela de menu, e é essa a razão de a lista ser longa.
ROTAS_DISPENSADAS = {
    '/pesquisa/importar_rpi_mais_recente/': (
        'ação mutável e dependente de serviço externo: a view executa, por GET, os comandos '
        '`importar_rpi` e `importar_rpi_software`, que consultam as revistas do INPI e gravam os '
        'despachos. O smoke não deve depender da rede nem repetir importações no banco reusado.'
    ),
    '/pesquisa/submeter_obra/<int:edital_id>/': (
        'o parâmetro é o **edital de publicação** (`EditalSubmissaoObra`), e o alvo genérico do smoke para '
        '`edital_id` é o edital do PESQUISA — abrir com ele dá 404. É exercitada por `test_13`, que a alcança '
        'pelo botão "Submeter Publicação" na listagem de editais abertos.'
    ),
    '/pesquisa/itens_selecionados_para_recursos/<int:projeto_id>/': (
        'HTTP 403 no smoke: `itens_selecionados_para_recursos` (views.py:8930) — guard de **estado da obra**: o smoke roda depois da cadeia, e esta etapa exige a obra num estado anterior. Exercitada pelos `test_12`→`test_14` quando o guard permite.'
    ),
    '/pesquisa/avaliar_diagramacao/<int:obra_id>/<int:opcao>/': (
        'HTTP 403 no smoke: `avaliar_diagramacao` (views.py:5460) — guard de **estado da obra**: o smoke roda depois da cadeia, e esta etapa exige a obra num estado anterior. Exercitada pelos `test_12`→`test_14` quando o guard permite.'
    ),
    '/pesquisa/cadastrar_diagramacao/<int:obra_id>/': (
        'HTTP 403 no smoke: `cadastrar_diagramacao` (views.py:5482) — guard de **estado da obra**: o smoke roda depois da cadeia, e esta etapa exige a obra num estado anterior. Exercitada pelos `test_12`→`test_14` quando o guard permite.'
    ),
    '/pesquisa/cadastrar_ficha_catalografica/<int:obra_id>/': (
        'HTTP 403 no smoke: `cadastrar_ficha_catalografica` (views.py:5570) — guard de **estado da obra**: o smoke roda depois da cadeia, e esta etapa exige a obra num estado anterior. Exercitada pelos `test_12`→`test_14` quando o guard permite.'
    ),
    '/pesquisa/cadastrar_isbn/<int:obra_id>/': (
        'HTTP 403 no smoke: `cadastrar_isbn` (views.py:5504) — guard de **estado da obra**: o smoke roda depois da cadeia, e esta etapa exige a obra num estado anterior. Exercitada pelos `test_12`→`test_14` quando o guard permite.'
    ),
    '/pesquisa/concluir_obra/<int:obra_id>/': (
        'HTTP 403 no smoke: `concluir_obra` (views.py:5588) — guard de **estado da obra**: o smoke roda depois da cadeia, e esta etapa exige a obra num estado anterior. Exercitada pelos `test_12`→`test_14` quando o guard permite.'
    ),
    '/pesquisa/enviar_arquivo_corrigido/<int:obra_id>/': (
        'HTTP 403 no smoke: `enviar_arquivo_corrigido` (views.py:5390) — guard de **estado da obra**: o smoke roda depois da cadeia, e esta etapa exige a obra num estado anterior. Exercitada pelos `test_12`→`test_14` quando o guard permite.'
    ),
    '/pesquisa/indicar_revisor_obra/<int:obra_id>/': (
        'HTTP 403 no smoke: `indicar_revisor_obra` (views.py:5341) — guard de **estado da obra**: o smoke roda depois da cadeia, e esta etapa exige a obra num estado anterior. Exercitada pelos `test_12`→`test_14` quando o guard permite.'
    ),
    '/pesquisa/parecerista_avaliar_obra/<int:obra_id>/': (
        'HTTP 403 no smoke: `parecerista_avaliar_obra` (views.py:5186) — guard de **estado da obra**: o smoke roda depois da cadeia, e esta etapa exige a obra num estado anterior. Exercitada pelos `test_12`→`test_14` quando o guard permite.'
    ),
    '/pesquisa/reenviar_obra/<int:obra_id>/': (
        'HTTP 403 no smoke: `reenviar_obra` (views.py:5255) — guard de **estado da obra**: o smoke roda depois da cadeia, e esta etapa exige a obra num estado anterior. Exercitada pelos `test_12`→`test_14` quando o guard permite.'
    ),
    '/pesquisa/revisar_obra/<int:obra_id>/': (
        'HTTP 403 no smoke: `revisar_obra` (views.py:5368) — guard de **estado da obra**: o smoke roda depois da cadeia, e esta etapa exige a obra num estado anterior. Exercitada pelos `test_12`→`test_14` quando o guard permite.'
    ),
    '/pesquisa/revisor_emitir_parecer/<int:obra_id>/': (
        'HTTP 403 no smoke: `revisor_emitir_parecer` (views.py:5414) — guard de **estado da obra**: o smoke roda depois da cadeia, e esta etapa exige a obra num estado anterior. Exercitada pelos `test_12`→`test_14` quando o guard permite.'
    ),
    '/pesquisa/editar_pi_parceira/<int:pi_id>/': (
        'HTTP 404 no smoke: `editar_pi_parceira` (views.py) — espera a parceria de PI e o seed não cria parceria.'
    ),
    '/pesquisa/editar_etapa_parceira/<int:etapa_id>/': (
        'HTTP 404 no smoke: `editar_etapa_parceira` (views.py) — o parâmetro é de parceria e o seed não cria parceria.'
    ),
    '/pesquisa/alterar_chefia_imediata/<int:projeto_id>/': (
        'HTTP 403 no smoke: `alterar_chefia_imediata` (views.py:7302) — é ação do coordenador do projeto e o smoke roda depois da cadeia, quando o projeto está finalizado — o guard recusa. Exercitada pelo fluxo quando o guard permite.'
    ),
    '/pesquisa/atualizar_pontuacao/<int:projeto_id>/': (
        'HTTP 403 no smoke: `atualizar_pontuacao` (views.py:3773) — mistura papéis: quem atualiza a pontuação é o avaliador/pré-avaliador do projeto, e o smoke abre como Diretor. Exercitada pelos `test_03`→`test_05`.'
    ),
    '/pesquisa/avaliar_conclusao_projeto_por_relatorio/<int:projeto_id>/': (
        'HTTP 403 no smoke: `avaliar_conclusao_projeto_por_relatorio` (views.py:8174) — exige o supervisor do projeto e o estado de conclusão registrada — o smoke roda depois da cadeia, quando a conclusão já foi validada. Exercitada por `test_11`.'
    ),
    '/pesquisa/divulgar_resultado_edital_parcial/<int:edital_id>/': (
        'HTTP 403 no smoke: `divulgar_resultado_edital_parcial` (views.py:4314) — exige `pode_gerenciar_edital` **e** o período de divulgação; fora dele a view recusa. Exercitada pela cadeia no período.'
    ),
    '/pesquisa/editar_projeto/<int:projeto_id>/': (
        'HTTP 403 no smoke: `editar_projeto` (views.py:2978) — só abre com o projeto em edição (rascunho) para o seu coordenador; o smoke roda depois da cadeia e o projeto está finalizado. Exercitada por `test_02`.'
    ),
    '/pesquisa/registro_conclusao/<int:projeto_id>/': (
        'HTTP 403 no smoke: `registro_conclusao` (views.py:1616) — como o anterior: exige o projeto em execução e o seu coordenador. Exercitada por `test_09`.'
    ),
    '/pesquisa/editar_etapa_parceira/<int:projeto_id>/': (
        'HTTP 404 no smoke: `?` (views.py:0) — o parâmetro é de `EditalParceria` (o nome do padrão diz `projeto_id`, mas a view busca a parceria) e o seed não cria parceria — 404 medido no smoke.'
    ),
    '/pesquisa/editar_pi_parceira/<int:projeto_id>/': (
        'HTTP 404 no smoke: `?` (views.py:0) — idem: espera a parceria de PI e o seed não a cria. 404 medido.'
    ),
    '/pesquisa/validar_cancelamento_projeto/<int:projeto_id>/': (
        'HTTP 404 no smoke: `validar_cancelamento_projeto` (views.py:4476) — espera um `CancelamentoProjeto` e o seed não cria cancelamento. 404 medido.'
    ),
    '/pesquisa/excluir_desembolsos/<int:projeto_id>/': (
        'HTTP 500 no smoke: `excluir_desembolsos` (views.py:7606) — **devolve 500 no GET** (achado do smoke, não dispensa por dificuldade): a view lê um parâmetro do caminho que o padrão não declara.'
    ),
    '/pesquisa/aceitar_termo_compromisso/<int:participacao_id>/': (
        'ação do ciclo de vida do projeto: o smoke roda **depois** da cadeia inteira, quando o projeto já está finalizado, e o guard da view (pertencimento ao projeto + estado) recusa. As rotas do gênero são exercitadas pelos `test_02`→`test_11` pelo botão, no momento em que o guard permite — e é essa a cobertura que a rota tem; o que falta aqui é o smoke poder reabri-la, e não critério de sucesso.'
    ),
    '/pesquisa/adicionar_projeto/<int:edital_id>/': (
        'ação do ciclo de vida do projeto: o smoke roda **depois** da cadeia inteira, quando o projeto já está finalizado, e o guard da view (pertencimento ao projeto + estado) recusa. As rotas do gênero são exercitadas pelos `test_02`→`test_11` pelo botão, no momento em que o guard permite — e é essa a cobertura que a rota tem; o que falta aqui é o smoke poder reabri-la, e não critério de sucesso.'
    ),
    '/pesquisa/adicionar_registro_diario_bordo/<int:projeto_id>/': (
        'ação do ciclo de vida do projeto: o smoke roda **depois** da cadeia inteira, quando o projeto já está finalizado, e o guard da view (pertencimento ao projeto + estado) recusa. As rotas do gênero são exercitadas pelos `test_02`→`test_11` pelo botão, no momento em que o guard permite — e é essa a cobertura que a rota tem; o que falta aqui é o smoke poder reabri-la, e não critério de sucesso.'
    ),
    '/pesquisa/cadastrar_frequencia/<int:projeto_id>/': (
        'ação do ciclo de vida do projeto: o smoke roda **depois** da cadeia inteira, quando o projeto já está finalizado, e o guard da view (pertencimento ao projeto + estado) recusa. As rotas do gênero são exercitadas pelos `test_02`→`test_11` pelo botão, no momento em que o guard permite — e é essa a cobertura que a rota tem; o que falta aqui é o smoke poder reabri-la, e não critério de sucesso.'
    ),
    '/pesquisa/cancelar_projeto/<int:projeto_id>/': (
        'ação do ciclo de vida do projeto: o smoke roda **depois** da cadeia inteira, quando o projeto já está finalizado, e o guard da view (pertencimento ao projeto + estado) recusa. As rotas do gênero são exercitadas pelos `test_02`→`test_11` pelo botão, no momento em que o guard permite — e é essa a cobertura que a rota tem; o que falta aqui é o smoke poder reabri-la, e não critério de sucesso.'
    ),
    '/pesquisa/classificar_trl/<int:projeto_id>/': (
        'ação do ciclo de vida do projeto: o smoke roda **depois** da cadeia inteira, quando o projeto já está finalizado, e o guard da view (pertencimento ao projeto + estado) recusa. As rotas do gênero são exercitadas pelos `test_02`→`test_11` pelo botão, no momento em que o guard permite — e é essa a cobertura que a rota tem; o que falta aqui é o smoke poder reabri-la, e não critério de sucesso.'
    ),
    '/pesquisa/clonar_projeto/<int:edital_id>/': (
        'ação do ciclo de vida do projeto: o smoke roda **depois** da cadeia inteira, quando o projeto já está finalizado, e o guard da view (pertencimento ao projeto + estado) recusa. As rotas do gênero são exercitadas pelos `test_02`→`test_11` pelo botão, no momento em que o guard permite — e é essa a cobertura que a rota tem; o que falta aqui é o smoke poder reabri-la, e não critério de sucesso.'
    ),
    '/pesquisa/enviar_recurso/<int:projeto_id>/': (
        'ação do ciclo de vida do projeto: o smoke roda **depois** da cadeia inteira, quando o projeto já está finalizado, e o guard da view (pertencimento ao projeto + estado) recusa. As rotas do gênero são exercitadas pelos `test_02`→`test_11` pelo botão, no momento em que o guard permite — e é essa a cobertura que a rota tem; o que falta aqui é o smoke poder reabri-la, e não critério de sucesso.'
    ),
    '/pesquisa/interpor_recurso/<int:projeto_id>/': (
        'ação do ciclo de vida do projeto: o smoke roda **depois** da cadeia inteira, quando o projeto já está finalizado, e o guard da view (pertencimento ao projeto + estado) recusa. As rotas do gênero são exercitadas pelos `test_02`→`test_11` pelo botão, no momento em que o guard permite — e é essa a cobertura que a rota tem; o que falta aqui é o smoke poder reabri-la, e não critério de sucesso.'
    ),
    '/pesquisa/desfazer_finalizacao_projeto/<int:projeto_id>/': (
        'é exercitada por `test_10`/`test_11` no momento certo, mas **não abre no smoke**: o smoke roda depois da cadeia inteira e o projeto já está finalizado, então o guard da view recusa. Comprova que a rota funciona o fato de o fluxo a alcançar pelo botão.'
    ),
    '/pesquisa/pre_aprovar/<int:projeto_id>/': (
        'é exercitada por `test_03` no período de pré-seleção, e **não abre no smoke**: quando ele roda, a cadeia já levou o projeto até a finalização e o guard da view recusa. A rota é coberta pelo fluxo, pelo botão.'
    ),
    '/pesquisa/pre_rejeitar/<int:projeto_id>/': (
        'irmã de `pre_aprovar`: só abre para projeto na pré-seleção e com o edital na janela. O fluxo a exercita pelo botão em `test_03`.'
    ),
    '/pesquisa/pre_selecionar/<int:projeto_id>/': (
        'é exercitada por `test_03` no período de pré-seleção, e **não abre no smoke**: a cadeia já finalizou o projeto quando ele roda. Coberta pelo fluxo.'
    ),
    '/pesquisa/projetos_nao_avaliados/<int:edital_id>/': (
        'é a tela que `test_03` abre pelo ícone de exibição, dentro da janela de pré-seleção. O smoke roda depois e o guard recusa.'
    ),
    '/pesquisa/selecionar_avaliadores_do_projeto/<int:projeto_id>/': (
        'é exercitada por `test_04` pelo botão "Selecionar avaliadores", na janela de seleção. O smoke roda depois da cadeia e o guard recusa.'
    ),
    '/pesquisa/validar_registros_frequencia/<int:projeto_id>/': (
        'é exercitada por `test_08` no monitoramento. O smoke roda depois e o guard recusa.'
    ),
    '/pesquisa/aceitar_doacao_editora/<int:doacao_id>/': (
        'exige `DoacaoEditora`, que o seed deste módulo não cria: `aceitar_doacao_editora` (views.py:10000). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/aceitar_indicacao/<int:projeto_id>/': (
        'ação que grava por **GET**: `aceitar_indicacao` (views.py:8112) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/aceitar_indicacao_parecerista_obra/<int:obra_id>/': (
        'ação que grava por **GET**: `aceitar_indicacao_parecerista_obra` (views.py:6864) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/acompanhar_solicitacao_servico/<int:solicitacao_id>/': (
        'exige `SolicitacaoServicoLaboratorio`, que o seed deste módulo não cria: `acompanhar_solicitacao_servico` (views.py:7791). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/adicionar_anexo/<int:edital_id>/': (
        'ação que grava por **GET**: `adicionar_anexo` (views.py:2420) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/adicionar_anexo_auxiliar/<int:edital_id>/': (
        'ação que grava por **GET**: `adicionar_anexo_auxiliar` (views.py:2402) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/adicionar_autor_obra/<int:obra_id>/<int:vinculo_id>/': (
        'exige `Obra`, que o seed deste módulo não cria: `adicionar_autor_obra` (views.py:5126). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/adicionar_criterio_avaliacao/<int:pk>/': (
        'ação que grava por **GET**: `adicionar_criterio_avaliacao` (views.py:2355) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/adicionar_desembolso/<int:projeto_id>/': (
        'ação que grava por **GET**: `adicionar_desembolso` (views.py:2551) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/adicionar_documento_parceria/<int:parceria_id>/<int:tipo>/': (
        'exige `Parceria`, que o seed deste módulo não cria: `adicionar_documento_parceria` (views.py:10502). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/adicionar_etapa/<int:meta_id>/': (
        'ação que grava por **GET**: `adicionar_etapa` (views.py:2227) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/adicionar_etapa_parceria/<int:parceria_id>/': (
        'exige `Parceria`, que o seed deste módulo não cria: `adicionar_etapa_parceria` (views.py:10541). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/adicionar_foto/<int:projeto_id>/': (
        'ação que grava por **GET**: `adicionar_foto` (views.py:2791) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/adicionar_membro_parceria/<int:parceria_id>/': (
        'exige `Parceria`, que o seed deste módulo não cria: `adicionar_membro_parceria` (views.py:10395). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/adicionar_meta/<int:projeto_id>/': (
        'ação que grava por **GET**: `adicionar_meta` (views.py:2172) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/adicionar_oferta_projeto/<int:edital_id>/': (
        'ação que grava por **GET**: `adicionar_oferta_projeto` (views.py:2490) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/adicionar_parceiro/<int:parceria_id>/': (
        'exige `Parceria`, que o seed deste módulo não cria: `adicionar_parceiro` (views.py:10367). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/adicionar_participante_aluno/<int:projeto_id>/': (
        'ação que grava por **GET**: `adicionar_participante_aluno` (views.py:1962) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/adicionar_participante_colaborador/<int:projeto_id>/': (
        'ação que grava por **GET**: `adicionar_participante_colaborador` (views.py:7922) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/adicionar_participante_servidor/<int:projeto_id>/': (
        'ação que grava por **GET**: `adicionar_participante_servidor` (views.py:1804) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/adicionar_pi_parceria/<int:parceria_id>/': (
        'exige `Parceria`, que o seed deste módulo não cria: `adicionar_pi_parceria` (views.py:10439). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/aprovar_projetos_com_bolsa/<int:edital_id>/<int:campus_id>/': (
        'exige `Edital`, que o seed deste módulo não cria: `aprovar_projetos_com_bolsa` (views.py:9656). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/arquivar_pi/<int:propriedade_id>/': (
        'exige `RegistroPropriedadeIntelectual`, que o seed deste módulo não cria: `arquivar_pi` (views.py:9141). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/ativar_participante/<int:participacao_id>/': (
        'ação que grava por **GET**: `ativar_participante` (views.py:2142) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/atualizar_curriculo_lattes/<int:edital_id>/': (
        'exige `Edital`, que o seed deste módulo não cria: `atualizar_curriculo_lattes` (views.py:4010). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/atualizar_grupos_de_pesquisa/': (
        'exige `CurriculoVittaeLattes`, que o seed deste módulo não cria: `atualizar_grupos_de_pesquisa` (views.py:3794). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/autorizar_edital/<int:edital_id>/<str:opcao>/': (
        'ação que grava por **GET**: `autorizar_edital` (views.py:4922) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/autorizar_projetos_sem_fomento/<int:edital_id>/': (
        'ação que grava por **GET**: `autorizar_projetos_sem_fomento` (views.py:9570) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/avaliar/<int:projeto_id>/': (
        'ação que grava por **GET**: `avaliar` (views.py:2022) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/avaliar_alteracao_equipe/<int:solicitacao_id>/': (
        'exige `SolicitacaoAlteracaoEquipe`, que o seed deste módulo não cria: `avaliar_alteracao_equipe` (views.py:7514). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/avaliar_cancelamento_projeto/<int:cancelamento_id>/': (
        'exige `ProjetoCancelado`, que o seed deste módulo não cria: `avaliar_cancelamento_projeto` (views.py:4066). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/avaliar_conclusao_projeto/<int:registro_id>/': (
        'exige `RegistroConclusaoProjeto`, que o seed deste módulo não cria: `avaliar_conclusao_projeto` (views.py:2768). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/avaliar_convite_recrutamento/<int:recrutamento_id>/<int:opcao>/': (
        'ação que grava por **GET**: `avaliar_convite_recrutamento` (views.py:10186) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/avaliar_executar_projeto/<int:projeto_id>/<int:opcao_id>/': (
        'ação que grava por **GET**: `avaliar_executar_projeto` (views.py:9608) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/avaliar_inclusao_equipe/<int:solicitacao_id>/': (
        'exige `SolicitacaoInclusaoEquipe`, que o seed deste módulo não cria: `avaliar_inclusao_equipe` (views.py:9432). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/avaliar_recrutamento/<int:recrutamento_id>/': (
        'exige `RecrutamentoAssessor`, que o seed deste módulo não cria: `avaliar_recrutamento` (views.py:10174). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/avaliar_recurso/<int:itemavaliacao_id>/': (
        'exige `ItemAvaliacao`, que o seed deste módulo não cria: `avaliar_recurso` (views.py:9001). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/avaliar_recurso_projeto/<int:recurso_id>/': (
        'exige `RecursoProjeto`, que o seed deste módulo não cria: `avaliar_recurso_projeto` (views.py:4132). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/avaliar_relatorio/<int:relatorio_id>/<int:situacao>/': (
        'exige `RelatorioProjeto`, que o seed deste módulo não cria: `avaliar_relatorio` (views.py:8142). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/avaliar_solicitacao/<int:solicitacao_id>/': (
        'exige `SolicitacaoServicoLaboratorio`, que o seed deste módulo não cria: `avaliar_solicitacao` (views.py:7690). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/cadastrar_documento_incubadora/<int:pk>/': (
        'exige `Incubadora`, que o seed deste módulo não cria: `cadastrar_documento_incubadora` (views.py:8573). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/cadastrar_documento_transferencia/<int:transferencia_id>/': (
        'exige `TransferenciaTecnologica`, que o seed deste módulo não cria: `cadastrar_documento_transferencia` (views.py:10839). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/cadastrar_empreendimento_incubadora/<int:pk>/': (
        'exige `Incubadora`, que o seed deste módulo não cria: `cadastrar_empreendimento_incubadora` (views.py:8519). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/cadastrar_evento_incubadora/<int:pk>/': (
        'exige `Incubadora`, que o seed deste módulo não cria: `cadastrar_evento_incubadora` (views.py:9232). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/cadastrar_foto_incubadora/<int:pk>/': (
        'exige `Incubadora`, que o seed deste módulo não cria: `cadastrar_foto_incubadora` (views.py:8619). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/cadastrar_membro_incubadora/<int:pk>/': (
        'exige `Incubadora`, que o seed deste módulo não cria: `cadastrar_membro_incubadora` (views.py:8484). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/cadastrar_recurso_transferencia/<int:transferencia_id>/': (
        'exige `TransferenciaTecnologica`, que o seed deste módulo não cria: `cadastrar_recurso_transferencia` (views.py:10795). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/cancelar_avaliacao_etapa/<int:registroexecucao_id>/': (
        'ação que grava por **GET**: `cancelar_avaliacao_etapa` (views.py:9951) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/cancelar_avaliacao_execucao_etapa/<int:registro_id>/': (
        'exige `RegistroExecucaoEtapa`, que o seed deste módulo não cria: `cancelar_avaliacao_execucao_etapa` (views.py:4773). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/cancelar_avaliacao_execucao_gasto/<int:registro_id>/': (
        'exige `RegistroGasto`, que o seed deste módulo não cria: `cancelar_avaliacao_execucao_gasto` (views.py:4791). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/cancelar_avaliacao_gasto/<int:registrogasto_id>/': (
        'ação que grava por **GET**: `cancelar_avaliacao_gasto` (views.py:9969) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/classificar_obra/<int:obra_id>/': (
        'ação que grava por **GET**: `classificar_obra` (views.py:6627) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/concluir_planejamento/<int:projeto_id>/': (
        'ação que grava por **GET**: `concluir_planejamento` (views.py:3130) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/concluir_solicitacao/<int:solicitacao_id>/': (
        'ação que grava por **GET**: `concluir_solicitacao` (views.py:7726) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/deletar_participante/<int:participacao_id>/': (
        'ação que grava por **GET**: `deletar_participante` (views.py:4522) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/desfazer_validacao_conselho/<int:obra_id>/': (
        'ação que grava por **GET**: `desfazer_validacao_conselho` (views.py:7443) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/desfazer_verificacao_antiplagio/<int:obra_id>/': (
        'ação que grava por **GET**: `desfazer_verificacao_antiplagio` (views.py:7417) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/despacho_lido/<int:despacho_id>/': (
        'ação que grava por **GET**: `despacho_lido` (views.py:8890) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/desvincular_secretario/<int:pk>/': (
        'ação que **apaga** por GET: `desvincular_secretario_programapos` (views.py:8398) faz `obj.delete()` sem `require_POST`, e abri-la no smoke apagaria registro do banco reusado. Exige `SecretarioProgramaPos`, de subdomínio que o seed não cria.'
    ),
    '/pesquisa/divulgar_resultado_edital_parcial/<int:edital_id>/<int:campus_id>/': (
        'exige `Edital`, que o seed deste módulo não cria: `divulgar_resultado_edital_parcial` (views.py:4314). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/editar_anexo/<int:anexo_id>/': (
        'ação que grava por **GET**: `editar_anexo` (views.py:2458) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/editar_anexo_auxiliar/<int:anexo_id>/': (
        'ação que grava por **GET**: `editar_anexo_auxiliar` (views.py:2474) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/editar_criterio_avaliacao/<int:pk>/': (
        'ação que grava por **GET**: `editar_criterio_avaliacao` (views.py:2385) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/editar_desembolso/<int:desembolso_id>/': (
        'ação que grava por **GET**: `editar_desembolso` (views.py:2611) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/editar_documento_incubadora/<int:pk>/': (
        'exige `DocumentoIncubadora`, que o seed deste módulo não cria: `editar_documento_incubadora` (views.py:8592). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/editar_documento_transferencia/<int:documento_id>/': (
        'exige `DocumentoTransferencia`, que o seed deste módulo não cria: `editar_documento_transferencia` (views.py:10856). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/editar_empreendimento_incubadora/<int:pk>/': (
        'exige `EmpreendimentoIncubadora`, que o seed deste módulo não cria: `editar_empreendimento_incubadora` (views.py:8538). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/editar_equipamento/<int:equipamento_id>/': (
        'exige `EquipamentoLaboratorioPesquisa`, que o seed deste módulo não cria: `editar_equipamento` (views.py:6692). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/editar_equipe_etapa/<int:etapa_id>/': (
        'ação que grava por **GET**: `editar_equipe_etapa` (views.py:2285) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/editar_etapa/<int:etapa_id>/': (
        'ação que grava por **GET**: `editar_etapa` (views.py:2263) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/editar_evento_incubadora/<int:pk>/': (
        'exige `EventoIncubadora`, que o seed deste módulo não cria: `editar_evento_incubadora` (views.py:9251). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/editar_foto/<int:foto_id>/': (
        'exige `FotoProjeto`, que o seed deste módulo não cria: `editar_foto` (views.py:8095). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/editar_foto_incubadora/<int:pk>/': (
        'exige `FotoIncubadora`, que o seed deste módulo não cria: `editar_foto_incubadora` (views.py:8638). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/editar_frequencia/<int:registrofrequencia_id>/': (
        'exige `RegistroFrequencia`, que o seed deste módulo não cria: `editar_frequencia` (views.py:8068). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/editar_material/<int:material_id>/': (
        'exige `MaterialLaboratorioPesquisa`, que o seed deste módulo não cria: `editar_material` (views.py:6725). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/editar_membro/<int:membro_id>/': (
        'exige `MembroParceria`, que o seed deste módulo não cria: `editar_membro` (views.py:10413). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/editar_membro_incubadora/<int:pk>/': (
        'exige `MembroIncubadora`, que o seed deste módulo não cria: `editar_membro_incubadora` (views.py:8498). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/editar_meta/<int:meta_id>/': (
        'ação que grava por **GET**: `editar_meta` (views.py:2193) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/editar_oferta_projeto/<int:oferta_projeto_id>/<int:edital_id>/': (
        'ação que grava por **GET**: `editar_oferta_projeto` (views.py:2532) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/editar_parceiro/<int:parceiro_id>/': (
        'exige `Parceiro`, que o seed deste módulo não cria: `editar_parceiro` (views.py:10382). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/editar_parceria/<int:parceria_id>/': (
        'exige `Parceria`, que o seed deste módulo não cria: `editar_parceria` (views.py:10338). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/editar_parecer/<int:parecerobra_id>/': (
        'exige `ParecerObra`, que o seed deste módulo não cria: `editar_parecer` (views.py:6785). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/editar_recurso/<int:recurso_id>/': (
        'ação que grava por **GET**: `editar_recurso` (views.py:2336) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/editar_recurso_transferencia/<int:recurso_id>/': (
        'exige `RecursoTransferencia`, que o seed deste módulo não cria: `editar_recurso_transferencia` (views.py:10812). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/editar_registro_diario_bordo/<int:registro_id>/': (
        'exige `RegistroDiarioBordo`, que o seed deste módulo não cria: `editar_registro_diario_bordo` (views.py:10655). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/editar_relatorio/<int:relatorio_id>/': (
        'exige `RelatorioProjeto`, que o seed deste módulo não cria: `editar_relatorio` (views.py:8211). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/editar_servico/<int:servico_id>/': (
        'exige `ServicoLaboratorioPesquisa`, que o seed deste módulo não cria: `editar_servico` (views.py:6659). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/editar_transferencia/<int:transferencia_id>/': (
        'exige `TransferenciaTecnologica`, que o seed deste módulo não cria: `editar_transferencia` (views.py:10779). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/editar_vinculo_membro_obra/<int:membro_id>/': (
        'exige `MembroObra`, que o seed deste módulo não cria: `editar_vinculo_membro_obra` (views.py:8723). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/emitir_certificado_assessor/<int:pk>/': (
        'exige `AssessorIncubadora`, que o seed deste módulo não cria: `emitir_certificado_assessor` (views.py:10224). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/emitir_certificado_pdf/<int:pk>/': (
        'exige `Participacao`, que o seed deste módulo não cria: `emitir_certificado_pdf` (views.py:4633). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/emitir_declaracao_assessor/<int:pk>/': (
        'exige `AssessorIncubadora`, que o seed deste módulo não cria: `emitir_declaracao_assessor` (views.py:10248). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/emitir_declaracao_avaliador_pdf/<int:pk>/': (
        'exige `Edital`, que o seed deste módulo não cria: `emitir_declaracao_avaliador_pdf` (views.py:4226). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/emitir_declaracao_orientacao_pdf/<int:pk>/': (
        'exige `Participacao`, que o seed deste módulo não cria: `emitir_declaracao_orientacao_pdf` (views.py:4674). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/emitir_declaracao_parecerista_pdf/<int:pk>/': (
        'exige `EditalSubmissaoObra`, que o seed deste módulo não cria: `emitir_declaracao_parecerista_pdf` (views.py:6896). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/emitir_declaracao_participacao_pdf/<int:pk>/': (
        'exige `Participacao`, que o seed deste módulo não cria: `emitir_declaracao_participacao_pdf` (views.py:4368). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/excluir_arquivo_parceria/<int:arquivo_id>/': (
        'ação que grava por **GET**: `excluir_arquivo_parceria` (views.py:10532) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/excluir_documento_incubadora/<int:pk>/': (
        'ação que grava por **GET**: `excluir_documento_incubadora` (views.py:8607) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/excluir_documento_transferencia/<int:documento_id>/': (
        'ação que grava por **GET**: `excluir_documento_transferencia` (views.py:10874) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/excluir_empreendimento_incubadora/<int:pk>/': (
        'ação que grava por **GET**: `excluir_empreendimento_incubadora` (views.py:8553) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/excluir_equipamento/<int:equipamento_id>/': (
        'ação que grava por **GET**: `excluir_equipamento` (views.py:6710) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/excluir_evento_incubadora/<int:pk>/': (
        'ação que grava por **GET**: `excluir_evento_incubadora` (views.py:9266) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/excluir_foto_incubadora/<int:pk>/': (
        'ação que grava por **GET**: `excluir_foto_incubadora` (views.py:8653) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/excluir_foto_laboratorio/<int:foto_id>/': (
        'ação que grava por **GET**: `excluir_foto_laboratorio` (views.py:6758) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/excluir_frequencia/<int:registrofrequencia_id>/': (
        'ação que grava por **GET**: `excluir_frequencia` (views.py:8083) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/excluir_integrante_equipe_tecnica/<int:assessor_id>/': (
        'ação que grava por **GET**: `excluir_integrante_equipe_tecnica` (views.py:10140) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/excluir_material/<int:material_id>/': (
        'ação que grava por **GET**: `excluir_material` (views.py:6743) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/excluir_membro/<int:membro_id>/': (
        'ação que grava por **GET**: `excluir_membro` (views.py:10430) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/excluir_membro_incubadora/<int:pk>/': (
        'ação que grava por **GET**: `excluir_membro_incubadora` (views.py:8510) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/excluir_outro_anexo/<int:anexo_id>/': (
        'ação que grava por **GET**: `excluir_outro_anexo` (views.py:6592) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/excluir_projeto_laboratorio/<int:projetolaboratorio_id>/': (
        'ação que grava por **GET**: `excluir_projeto_laboratorio` (views.py:9302) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/excluir_recurso_transferencia/<int:recurso_id>/': (
        'ação que grava por **GET**: `excluir_recurso_transferencia` (views.py:10830) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/excluir_registro_diario_bordo/<int:registro_id>/': (
        'ação que grava por **GET**: `excluir_registro_diario_bordo` (views.py:10685) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/excluir_relatorio/<int:relatorio_id>/': (
        'ação que grava por **GET**: `excluir_relatorio` (views.py:8199) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/excluir_servico/<int:servico_id>/': (
        'ação que grava por **GET**: `excluir_servico` (views.py:6679) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/ficha_avaliacao_obra/<int:parecer_id>/': (
        'exige `ParecerObra`, que o seed deste módulo não cria: `ficha_avaliacao_obra` (views.py:8227). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/filtrar_editais_completos_por_ano/': (
        'fragmento ajax: `filtrar_editais_completos_por_ano` (views.py:4908) devolve JSON para o seletor de ano, sem página própria.'
    ),
    '/pesquisa/filtrar_editais_por_ano/': (
        'fragmento ajax: `filtrar_editais_por_ano` (views.py:4894) devolve JSON (content-type application/json) para o seletor de ano da tela, sem página própria.'
    ),
    '/pesquisa/finalizar_conclusao/<int:projeto_id>/': (
        'ação que grava por **GET**: `finalizar_conclusao` (views.py:3236) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/finalizar_registro_diario_bordo/<int:registro_id>/': (
        'ação que grava por **GET**: `finalizar_registro_diario_bordo` (views.py:10672) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/finalizar_vinculo_assessor/<int:assessorincubadora_id>/': (
        'exige `AssessorIncubadora`, que o seed deste módulo não cria: `finalizar_vinculo_assessor` (views.py:10208). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/gerenciar_bolsas/<int:edital_id>/<int:campus_id>/': (
        'exige `Edital`, que o seed deste módulo não cria: `gerenciar_bolsas` (views.py:3387). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/importar_rpi_especifica/<int:numero_rpi>/': (
        'depende de serviço externo: `importar_rpi_especifica` (views.py:9216) chama os comandos `importar_rpi` e `importar_rpi_software`, que consultam as revistas do INPI. Não há dado local que a faça responder.'
    ),
    '/pesquisa/imprimir_diario_bordo/<int:pk>/': (
        'gera documento: `imprimir_diario_bordo` (views.py:10706) é decorada com `@documento(...)`, e o smoke não tem asserção possível além do content-type.'
    ),
    '/pesquisa/incubadora/<int:pk>/': (
        'exige `Incubadora`, que o seed deste módulo não cria: `incubadora` (views.py:8473). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/informar_pagamento_anuidade/<int:anuidade_id>/': (
        'exige `AnuidadeRegistroPropriedadeIntelectual`, que o seed deste módulo não cria: `informar_pagamento_anuidade` (views.py:9121). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/informar_responsavel_anuidade/<int:anuidade_id>/': (
        'exige `AnuidadeRegistroPropriedadeIntelectual`, que o seed deste módulo não cria: `informar_responsavel_anuidade` (views.py:10271). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/memoria_calculo/<int:projeto_id>/': (
        'ação que grava por **GET**: `memoria_calculo` (views.py:1564) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/parceria/<int:parceria_id>/': (
        'exige `Parceria`, que o seed deste módulo não cria: `parceria` (views.py:10354). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/programapos/<int:pk>/': (
        'exige `ProgramaPosGraduacao`, que o seed deste módulo não cria: `programapos` (views.py:8321). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/reativar_projeto/<int:projeto_id>/': (
        'ação que grava por **GET**: `reativar_projeto` (views.py:7457) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/recrutar_assessor/<int:assessor_id>/': (
        'exige `IntegranteEquipeTecnica`, que o seed deste módulo não cria: `recrutar_assessor` (views.py:10148). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/recurso_projeto/<int:recurso_id>/': (
        'exige `RecursoProjeto`, que o seed deste módulo não cria: `recurso_projeto` (views.py:4202). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/reenviar_convite_avaliador/<int:avaliador_id>/': (
        'ação que grava por **GET**: `reenviar_convite_avaliador` (views.py:9815) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/refazer_distribuicao_bolsas/<int:edital_id>/': (
        'ação que grava por **GET**: `refazer_distribuicao_bolsas` (views.py:4848) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/registrar_anuencia/<int:projeto_id>/<str:opcao>/': (
        'ação que grava por **GET**: `registrar_anuencia` (views.py:7275) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/registrar_conclusao_obra/<int:obra_id>/': (
        'ação que grava por **GET**: `registrar_conclusao_obra` (views.py:5525) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/registro_execucao_etapa/<int:etapa_id>/': (
        'ação que grava por **GET**: `registro_execucao_etapa` (views.py:1695) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/registro_gasto/<int:item_id>/': (
        'ação que grava por **GET**: `registro_gasto` (views.py:1635) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/rejeitar_indicacao/<int:projeto_id>/': (
        'ação que grava por **GET**: `rejeitar_indicacao` (views.py:6436) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/rejeitar_indicacao_parecerista_obra/<int:obra_id>/': (
        'ação que grava por **GET**: `rejeitar_indicacao_parecerista_obra` (views.py:6849) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/relacionar_processo_pi/<int:servico_id>/': (
        'exige `ServicoRegistroPropriedadeIntelectual`, que o seed deste módulo não cria: `relacionar_processo_pi` (views.py:9093). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/relacionar_processo_pi_anuidade/<int:anuidade_id>/': (
        'exige `AnuidadeRegistroPropriedadeIntelectual`, que o seed deste módulo não cria: `relacionar_processo_pi_anuidade` (views.py:9107). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/remover_anexo/<int:anexo_id>/': (
        'ação que grava por **GET**: `remover_anexo` (views.py:2438) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/remover_anexo_auxiliar/<int:anexo_id>/': (
        'ação que grava por **GET**: `remover_anexo_auxiliar` (views.py:2448) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/remover_criterio_avaliacao/<int:pk>/': (
        'ação que grava por **GET**: `remover_criterio_avaliacao` (views.py:2373) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/remover_desembolso/<int:desembolso_id>/': (
        'ação que grava por **GET**: `remover_desembolso` (views.py:2632) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/remover_etapa/<int:etapa_id>/': (
        'ação que grava por **GET**: `remover_etapa` (views.py:2250) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/remover_foto/<int:foto_id>/': (
        'ação que grava por **GET**: `remover_foto` (views.py:2818) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/remover_indicacao_avaliador/<int:avaliador_id>/': (
        'ação que grava por **GET**: `remover_indicacao_avaliador` (views.py:9065) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/remover_indicacoes_rejeitadas/<int:edital_id>/': (
        'ação que grava por **GET**: `remover_indicacoes_rejeitadas` (views.py:9861) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/remover_meta/<int:meta_id>/': (
        'ação que grava por **GET**: `remover_meta` (views.py:2214) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/remover_oferta_projeto/<int:oferta_projeto_id>/': (
        'ação que grava por **GET**: `remover_oferta_projeto` (views.py:2522) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/remover_parecerista/<int:parecerobra_id>/': (
        'ação que grava por **GET**: `remover_parecerista` (views.py:6141) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/remover_recurso/<int:recurso_id>/': (
        'ação que grava por **GET**: `remover_recurso` (views.py:2326) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/reprovar_execucao_etapa/<int:registroetapa_id>/': (
        'exige `RegistroExecucaoEtapa`, que o seed deste módulo não cria: `reprovar_execucao_etapa` (views.py:1763). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/reprovar_execucao_gasto/<int:gasto_id>/': (
        'exige `RegistroGasto`, que o seed deste módulo não cria: `reprovar_execucao_gasto` (views.py:1784). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/responder_autoavaliacao_programapos/<int:pk>/': (
        'exige `AutoavaliacaoProgramaPos`, que o seed deste módulo não cria: `responder_autoavaliacao_programapos` (views.py:8335). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/respostas_autoavaliacao_programapos/<int:pk>/': (
        'exige `AutoavaliacaoProgramaPos`, que o seed deste módulo não cria: `respostas_autoavaliacao_programapos` (views.py:8367). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/salvar_avaliadores_do_projeto/<int:projeto_id>/': (
        'ação que grava por **GET**: `salvar_avaliadores_do_projeto` (views.py:3718) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/transferencia_visualizar/<int:transferencia_id>/': (
        'exige `TransferenciaTecnologica`, que o seed deste módulo não cria: `transferencia_visualizar` (views.py:8767). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/upload_anexo/<int:anexo_id>/': (
        'exige `ProjetoAnexo`, que o seed deste módulo não cria: `upload_anexo` (views.py:2663). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/upload_anexo_auxiliar/<int:anexo_id>/': (
        'ação que grava por **GET**: `upload_anexo_auxiliar` (views.py:2707) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/upload_edital/<int:edital_id>/': (
        'ação que grava por **GET**: `upload_edital` (views.py:2735) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/validar_execucao_etapa/<int:projeto_id>/': (
        'ação que grava por **GET**: `validar_execucao_etapa` (views.py:1729) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/validar_frequencia/<int:registrofrequencia_id>/': (
        'ação que grava por **GET**: `validar_frequencia` (views.py:7577) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/validar_parecerista/<int:pessoaexternaobra_id>/<str:opcao>/': (
        'ação que grava por **GET**: `validar_parecerista` (views.py:7872) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/validar_projeto_fluxo_simplificado/<int:projeto_id>/<str:opcao>/': (
        'ação que grava por **GET**: `validar_projeto_fluxo_simplificado` (views.py:6807) salva sem `require_POST`, e abri-la no smoke gravaria no banco reusado (a suíte não dá flush) e corromperia a cadeia dos test_NN_*.'
    ),
    '/pesquisa/validar_recurso_projeto/<int:recurso_id>/': (
        'exige `RecursoProjeto`, que o seed deste módulo não cria: `validar_recurso_projeto` (views.py:4150). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/ver_empreendimento_incubadora/<int:pk>/': (
        'exige `EmpreendimentoIncubadora`, que o seed deste módulo não cria: `ver_empreendimento_incubadora` (views.py:8565). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/ver_pessoa_externa/<int:pessoaexternaobra_id>/': (
        'exige `PessoaExternaObra`, que o seed deste módulo não cria: `ver_pessoa_externa` (views.py:7914). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/vincular_area/<int:pk>/': (
        'exige `ProgramaPosGraduacao`, que o seed deste módulo não cria: `vincular_area_concentracao_programapos` (views.py:8441). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/vincular_curso/<int:pk>/': (
        'exige `ProgramaPosGraduacao`, que o seed deste módulo não cria: `vincular_curso_programapos` (views.py:8457). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/vincular_docente/<int:pk>/': (
        'exige `ProgramaPosGraduacao`, que o seed deste módulo não cria: `vincular_docente_programapos` (views.py:8417). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/vincular_secretario/<int:pk>/': (
        'exige `ProgramaPosGraduacao`, que o seed deste módulo não cria: `vincular_secretario_programapos` (views.py:8380). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/visualizar_arquivo/<int:arquivo_id>/': (
        'exige `Arquivo`, que o seed deste módulo não cria: `visualizar_arquivo` (views.py:2755). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/visualizar_assessor/<int:assessor_id>/': (
        'exige `IntegranteEquipeTecnica`, que o seed deste módulo não cria: `visualizar_assessor` (views.py:10126). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/visualizar_despachos_propriedade/<int:propriedade_id>/': (
        'exige `RegistroPropriedadeIntelectual`, que o seed deste módulo não cria: `visualizar_despachos_propriedade` (views.py:8881). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/visualizar_ficha_avaliacao/<int:avaliacao_id>/': (
        'exige `Avaliacao`, que o seed deste módulo não cria: `visualizar_ficha_avaliacao` (views.py:2050). É subdomínio cuja montagem é sessão própria.'
    ),
    '/pesquisa/visualizar_registro_diario_bordo/<int:pk>/': (
        'exige `RegistroDiarioBordo`, que o seed deste módulo não cria: `visualizar_registro_diario_bordo` (views.py:10698). É subdomínio cuja montagem é sessão própria.'
    ),
}
