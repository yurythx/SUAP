"""Fixtures compartilhadas dos testes e2e (pytest + Playwright + ``live_server``).

**Como usar num módulo**: crie ``<modulo>/tests/e2e/conftest.py`` com

    from djtools.e2e_fixtures import *  # noqa: F403

Mesmo idioma dos 54 ``<app>/features/environment.py`` do behave
(``from djtools.new_tests.environment_base import *``). O star-import registra as
fixtures no conftest, e conftest tem precedência sobre plugin — o que importa porque
duas fixtures aqui **sobrescrevem** o pytest-django (``_django_db_helper`` e
``django_db_modify_db_settings``) e essa precedência é o que faz a suíte funcionar.

Deliberadamente NÃO é registrado como plugin global (nem em ``pytest_plugins`` do
conftest raiz): o override no-op de ``_django_db_helper`` desligaria o wrapper de
transação do pytest-django na suíte **inteira**, e o sufixo ``_e2e`` mandaria os testes
unitários para o banco errado. O escopo por diretório é o que contém o estrago.

Coexiste com o behave de ``djtools/new_tests/`` — nada aqui toca aquela suíte. A
diferença que justifica esta suíte: o behave usa UM
``chromium.launch_persistent_context`` para a run inteira
(``djtools/new_tests/environment_base.py:399``), então sessão de browser e estado de
banco são compartilhados por todos os cenários e a ordem passa a importar. Aqui cada
teste ganha um contexto novo (cookies/sessão limpos) via ``new_context``.

Como rodar::

    TEST_DATABASE_NAME=test_suap_e2e DJANGO_SETTINGS_MODULE=suap.settings_test \
        uv run pytest -m e2e --reuse-db

``TEST_DATABASE_NAME`` com ``_e2e`` é **obrigatório** (há um guard que falha alto sem
ele): o banco do e2e não pode ser o mesmo da suíte unitária. E a invocação é sempre
separada da unitária — o job ``e2e`` do CI e o ``-m "not e2e"`` do ``suap_check``
garantem isso.

Pré-requisito: um Postgres com ``max_locks_per_transaction`` alto (ver docstring de
``suap/settings_test.py``). ``collectstatic`` **não** é necessário — verificado com
STATIC_ROOT vazio: como ``settings_test`` desliga o bundling do pipeline (ver o comentário
lá), os templates referenciam os arquivos-fonte e os finders os servem direto dos
``<app>/static/``.
"""

import os
import re
import sys
from datetime import date
from pathlib import Path
from collections.abc import Iterable, Iterator, Mapping
from typing import TYPE_CHECKING

# O loop greenlet do Playwright sync dispara o @async_unsafe do Django em
# ensure_connection. Precisa valer ANTES de qualquer conexão, ou seja em import-time
# (coleta) e não numa fixture. Mesmo motivo de environment_base.py:378.
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')

import pytest
from freezegun import freeze_time
from playwright.sync_api import Page, expect

# Importar a camada `Tela` aqui não é só pelo teto de navegação: é o que garante que o
# `expect.set_options` de lá rode em TODA suíte e2e. Este módulo é star-importado por todo
# conftest de e2e; `e2e_ui` é importado pelos testes, um a um.
from djtools.e2e_ui import TEMPO_ESPERA, TEMPO_NAVEGACAO, Tela

if TYPE_CHECKING:
    from pytest_django import DjangoDbBlocker

    from comum.models import Vinculo
    from edu.models import Aluno
    from rh.models import Servidor, Setor

# __all__ é OBRIGATÓRIO aqui, e tem de listar os nomes com underscore: `import *` não
# exporta nomes privados, então sem isto o `_django_db_helper` — a peça que desliga o
# flush por teste — não chegaria ao conftest do módulo. O sintoma é traiçoeiro: a suíte
# roda, o pytest-django volta a dar flush em cada teste, e os testes falham por "usuário
# não existe" em vez de acusar a fixture faltando.
__all__ = [
    'Relogio',
    '_django_db_helper',
    '_exige_banco_de_e2e',
    'abrir_popup',
    'aquecer_urlconf',
    'base_url',
    'capturas',
    'e2e_banco',
    'e2e_seed',
    'escolher_autocomplete',
    'live_server',
    'logado',
    'login_ui',
    'mensagem_de_erro',
    'mensagem_de_sucesso',
    'popup_em',
    'storage_states',
]

# Senha de todo usuário semeado (``semear_base``/``servidor_com_login``), inclusive o ``admin``.
# É a que ``login_ui``/``logado`` usam quando o teste não passa outra.
SENHA_E2E = 'abc'

# Sigla do setor raiz. Tem de bater com a ``Configuracao`` ``reitoria_sigla``: é por ela que
# ``Setor.raiz_suap`` acha a raiz.
SIGLA_RAIZ = 'RAIZ'

# Desktop fixo das capturas da doc de usuário: a largura é o que precisa ser estável entre
# regerações (a altura vem do `full_page`, senão todo formulário longo do SUAP sairia
# cortado ao meio).
VIEWPORT_DOC = {'width': 1440, 'height': 900}

# Teto de cada dimensão no formato WebP (libwebp).
LIMITE_WEBP = 16383

# `.fancybox-active` no `<body>` é o sinal de modal ABERTO — o fancybox tira a classe ao
# fechar, enquanto o `.fancybox-container` sobra escondido no DOM depois de fechado.
# O `?.` não é defensivo à toa: com navegação em voo (o `select` de período em
# `edu/tests/doc/test_06_diario.py` recarrega a página) o `evaluate` cai no documento novo
# ainda sem `<body>` e `document.body` é `null`. `false` é a resposta certa aí — modal não
# sobrevive a recarga —, e o `screenshot` seguinte já espera a página assentar sozinho.
MODAL_ABERTO = "() => document.body?.classList.contains('fancybox-active') ?? false"


def capturas(destino):
    """Devolve a fixture ``capturar`` que grava as telas de UM módulo em ``destino``.

    Fábrica e não fixture pronta porque o destino é por módulo — o conftest do módulo é quem
    o conhece::

        DESTINO = Path(settings.BASE_DIR) / 'eventos' / 'docs' / 'usuario'
        capturar = capturas(DESTINO)

    **Limpa o destino uma vez por sessão**, capturas e ``anotacoes.txt`` (que ``anotar`` abre
    em modo append). Sem isso, renomear uma captura deixa a antiga para trás e o diretório
    passa a misturar duas gerações — aconteceu com ``participante-pendente.webp``.

    A limpeza é da SESSÃO e não do arquivo de teste: numa run `pytest -m doc` inteira os 11
    arquivos de ``edu/tests/doc/`` são uma geração só, e limpar por arquivo apagaria o que o
    anterior produziu.

    Compartilhada de propósito: era o mesmo bloco copiado em cada ``<modulo>/tests/doc/``, e
    a cópia do ``edu`` tinha divergido — não limpava, porque nasceu quando cada arquivo era
    uma invocação separada do pytest. Com 90 módulos pela frente, divergência de cópia é a
    falha esperada, não a exceção.
    """
    destino = Path(destino)

    @pytest.fixture(scope='session')
    def capturar():
        from io import BytesIO

        from django.conf import settings
        from PIL import Image

        # A doc de usuário é do sistema como o usuário o vê: sem a barra `#debug` (que ainda
        # por cima expõe caminho do projeto e banco) e sem o `body.debug`, que troca o tema
        # para o vinho de desenvolvimento e injeta os avisos de `dev.css`. Só a RENDERIZAÇÃO
        # muda: `settings_test.DEBUG = True` existe para o django-pipeline, que resolve
        # `PIPELINE_ENABLED = not DEBUG` no *import* — desligar aqui, em tempo de execução,
        # não religa o bundling e o CSS/JS continua vindo dos finders.
        debug_original, settings.DEBUG = settings.DEBUG, False

        destino.mkdir(parents=True, exist_ok=True)
        for antiga in (*destino.glob('*.webp'), destino / 'anotacoes.txt'):
            antiga.unlink(missing_ok=True)
        feitas = []

        def _capturar(pagina, nome: str) -> Path:
            pagina.set_viewport_size(VIEWPORT_DOC)
            modal_aberto = pagina.evaluate(MODAL_ABERTO)
            caminho = destino / f'{nome}.webp'
            # Com modal aberto a captura é do VIEWPORT, não da página inteira: o esmaecer é um
            # `.fancybox-container` fixo de `height: 100%`, então no `full_page` ele parava nos
            # 900 px do viewport e o resto da página saía sem esmaecer (medido: esmaecer até
            # 1385 px numa captura de 1634 px). Forçá-lo a `absolute` com a altura do documento
            # foi tentado e não resolve: o `body` está em `overflow: hidden`
            # (`body.compensate-for-scrollbar`) enquanto o modal está aberto, a altura computada
            # do container ignorou o `height` com `!important` e a pintura parou nos mesmos
            # 1385 px. E não há o que perder na captura do viewport: a página atrás está
            # esmaecida de propósito, e o diálogo é dimensionado para caber na tela.
            imagem = Image.open(BytesIO(pagina.screenshot(full_page=not modal_aberto)))
            # O WebP não codifica além de 16383 px em nenhuma dimensão, e listagem longa
            # (boletim de turma cheia, calendário anual de eventos) passa disso — medido,
            # `ValueError: encoding error 5`. Cortar é melhor que cair para PNG: acima de uma
            # tela e meia a captura já não serve de ilustração.
            if imagem.height > LIMITE_WEBP:
                imagem = imagem.crop((0, 0, imagem.width, LIMITE_WEBP))
            imagem.save(caminho, 'WEBP', quality=80)
            feitas.append(caminho)
            return caminho

        yield _capturar

        total = sum(caminho.stat().st_size for caminho in feitas)
        # stderr direto: o hook `prints` do pre-commit proíbe print(), e o conftest raiz
        # desliga o logging.
        sys.stderr.write(f'\n[doc] {len(feitas)} capturas, {total / 1024:.0f} KiB no total, em {destino}\n')
        settings.DEBUG = debug_original

    return capturar


def escolher_autocomplete(page: Page, campo: str, texto: str, escopo=None, indice: int = 0, opcao=None) -> None:
    """Preenche um autocomplete select2 ancorado pelo ``name`` do select original.

    O ``id`` do select é aleatório a cada render (o SUAP monta o widget por JS), então o
    ``name`` é o único âncora estável. ``indice`` serve para as telas que repetem o mesmo
    ``name`` em quadros diferentes (formulários de etapa, por exemplo).

    ``opcao`` é o texto usado para escolher entre os resultados, e por padrão é o próprio
    ``texto`` digitado. Separá-los importa quando o campo é pesquisável por um valor que
    **não aparece** no rótulo do resultado — o autocomplete de Matriz/Curso, por exemplo,
    busca pelo código do curso mas exibe "Matriz: N - <descrição>". Passar ``opcao=''``
    aceita o primeiro resultado, seja ele qual for, e passar um ``re.Pattern`` permite
    ancorar o rótulo — necessário quando o resultado mostra também o registro pai e a
    busca casaria com o filho (setor "CODE/CEN (DIDE/CEN)" ao procurar "DIDE/CEN").

    ``escopo`` é o ``FrameLocator`` quando o formulário está dentro de um popup (ver
    ``abrir_popup``); ``page`` continua sendo necessário porque a digitação vai pelo
    teclado, que é do browser e não do frame.
    """
    escopo = escopo or page
    widget = escopo.locator(f'select[name="{campo}"] + span.select2').nth(indice)
    expect(widget).to_be_visible()
    widget.click()
    # Duas corridas diferentes, uma antes e outra depois de digitar. Ambas produziam flake
    # intermitente e ambas precisam ser esperadas — este bloco é a união de duas correções.
    #
    # ANTES: `keyboard.type` entrega cada tecla a quem estiver focado NAQUELE instante.
    # Enquanto o select2 não montou sua caixa de busca, o foco ainda é do campo anterior e as
    # primeiras teclas vazam para lá. Sintoma silencioso — um curso salvo com
    # `codigo='97313çã'`, onde `çã` é o miolo de "Especializa*çã*o" digitado no autocomplete
    # seguinte. ~50% de flake em `edu/tests/doc/test_02_curso.py`, e corrupção calada onde o
    # campo não era asserido.
    expect(escopo.locator('span.select2-container--open').first).to_be_visible()
    busca = escopo.locator('span.select2-search--dropdown input')
    if busca.count():
        busca.first.fill(texto)
    else:
        # Select2 sem caixa de busca (lista curta): aqui o teclado é seguro, porque o dropdown
        # já está aberto e o foco parou de se mover.
        page.keyboard.type(texto)
    # DEPOIS: o select2 pinta a linha "Searching…" (`.loading-results`) enquanto o AJAX corre e
    # só então a troca pelos resultados. Sem esperar, o clique pega o que estiver na lista
    # naquele instante: com `opcao=''` (rótulo vazio casa qualquer linha) ele cai
    # silenciosamente na linha de carregamento ou num resultado da busca anterior, e o teste
    # segue com o objeto errado. Raiz dos flakes de test_03/test_04/test_11 do edu, que só
    # apareciam quando o banco tinha candidatos suficientes para a busca demorar.
    expect(escopo.locator('.select2-results__option.loading-results')).to_have_count(0)
    escopo.locator('.select2-results__option', has_text=texto if opcao is None else opcao).first.click()


def abrir_popup(page: Page, nome_link: str):
    """Clica num link ``.popup`` e devolve o ``FrameLocator`` do formulário aberto.

    Popup no SUAP é um iframe do fancybox — não uma janela nova (é o mesmo que o step
    ``olho para o popup`` do behave faz em ``djtools/new_tests/common_steps/when.py``).
    Ao submeter, a view responde com ``close_popup=True``: o iframe fecha e a mensagem de
    sucesso aparece na página **de trás**, não no frame.
    """
    page.get_by_role('link', name=nome_link).first.click()
    frame = page.frame_locator('iframe.fancybox-iframe')
    expect(frame.locator('body')).to_be_visible()
    return frame


def popup_em(tela: Tela, rota: str) -> Tela:
    """Devolve a ``Tela`` do popup (iframe do fancybox) já carregado **na rota** esperada.

    Complementa ``abrir_popup``: aqui o popup foi aberto pelo caminho do teste (um item de menu
    "Ações", por exemplo) e o que se espera é o documento do iframe ter chegado na rota. O fancybox
    cria o ``iframe`` **antes** de carregar a URL, então esperar só o ``body`` visível acha um
    ``about:blank`` — e o popup real chega depois. A espera é pelo documento já na rota (e com
    ``form``), não por tempo fixo, porque a URL muda antes de o formulário existir — e aí o
    preenchimento morre em "element not found".

    Promovido de ``centralservicos/tests/doc/conftest.py`` quando o segundo consumidor apareceu
    (``centralservicos/tests/e2e/conftest.py``), como manda a receita para helper reusável.
    """
    tela.pagina.wait_for_function(
        """([rota]) => {
            const f = document.querySelector('iframe.fancybox-iframe');
            if (!f || !f.contentWindow.location.href.includes(rota)) return false;
            try { return !!f.contentDocument.querySelector('form'); } catch (e) { return false; }
        }""",
        arg=rota,
    )
    return tela.popup()


def aquecer_urlconf() -> None:
    """Importa ``suap/urls.py`` **antes** do primeiro ``freeze_time``. Chame antes de congelar.

    ``freeze_time`` troca ``datetime.date`` por ``FakeDate`` no módulo ``datetime``, e
    ``suap/urls.py`` importa ``suap/api.py``, que monta os schemas pydantic do django-ninja —
    o pydantic não reconhece ``FakeDate`` e estoura ``PydanticSchemaGenerationError``. Como
    esse import é preguiçoso (só na primeira request), sem o aquecimento ele cai **dentro**
    do congelamento. Pior: o import falho deixa ``suap.api`` pela metade e toda request
    seguinte passa a falhar com ``ConfigError: Router@'' has already been attached`` — o
    sintoma não aponta para o relógio.

    Promovido do ``edu`` quando o ``pesquisa`` virou o segundo módulo a congelar o relógio.
    """
    from django.urls import get_resolver

    assert get_resolver().url_patterns, 'urlconf vazia: o aquecimento não importou suap/urls.py'


class Relogio:
    """Congelador de data do **processo inteiro**, reutilizável dentro da sessão.

    Existe para módulos cujo domínio vive numa data passada: o behave fixava a data com
    ``Quando a data do sistema for "dd/mm/aaaa"`` e o seed, os calendários e as etapas de
    todo o módulo são montados nessa data. Aqui o congelamento é do processo, então a thread
    do ``live_server`` enxerga a mesma data que o teste.

    Três decisões que vêm de medição, não de desenho:

    1. **O relógio é da SESSÃO, não do teste.** A sessão de login é validada contra
       ``expire_date`` no banco: um cookie emitido sob uma data e lido sob outra é uma sessão
       expirada, e o sintoma é um redirect silencioso para ``/accounts/login/`` — não um erro
       de relógio. Consequência obrigatória: quem congela **não pode** usar o
       ``storage_states`` daqui, e faz login de verdade a cada teste (o que só é barato por
       causa do hasher MD5 de ``suap/settings_test.py``).
    2. **``tick=True``**, como o behave (``common_steps/when.py:158``): o relógio anda a
       partir da data fixada. Sem isso, qualquer código que meça duração enxerga delta zero.
    3. **``aquecer_urlconf()`` antes de congelar** — ver a docstring de lá.

    O que fica com o conftest do módulo, porque é decisão dele: a data base, os hooks
    ``pytest_runtest_setup``/``pytest_runtest_teardown`` que soltam o relógio ao sair do
    diretório (senão a data vaza para as suítes coletadas depois numa run `pytest -m e2e`) e
    a fixture ``autouse`` que congela a data que cada arquivo declara em ``DATA``.

    ``execute_steps`` é o adaptador mínimo para reusar os ``given.py`` do behave sem subir o
    behave: os seeds do ``edu`` andam com a data chamando
    ``context.execute_steps('Quando a data do sistema for ...')``.
    """

    def __init__(self) -> None:
        self._congelador = None
        self._data: str | None = None
        self._suspensa: str | None = None

    def congelar(self, data_br: str) -> None:
        """Fixa a data do processo — inclusive a thread do ``live_server``.

        Aceita ``dd/mm/aaaa`` ou ``dd/mm/aaaa HH:MM``. A hora é opcional porque um dos
        consumidores (``projetos/tests/doc``) precisa fixar um horário para que a captura de
        tela não caia num limite de dia; quem só passa a data fica à meia-noite.
        """
        self.descongelar()
        data, _, hora = data_br.strip().partition(' ')
        dia, mes, ano = data.split('/')
        self._congelador = freeze_time(f'{ano}-{mes}-{dia} {hora or "00:00"}', tick=True)
        self._congelador.start()
        self._data = data_br

    def descongelar(self) -> None:
        if self._congelador is not None:
            self._congelador.stop()
            self._congelador = None

    def suspender(self) -> None:
        """Solta o relógio ao sair do módulo, lembrando a data para ``retomar``."""
        if self._congelador is not None:
            self._suspensa = self._data
            self.descongelar()

    def retomar(self) -> None:
        if self._suspensa is not None:
            self.congelar(self._suspensa)
            self._suspensa = None

    def execute_steps(self, texto: str) -> None:
        """Interface mínima do ``context`` do behave usada pelos ``given.py`` dos módulos."""
        data = re.search(r'"(\d{2}/\d{2}/\d{4})"', texto)
        assert data, f'step não suportado fora do behave: {texto!r}'
        self.congelar(data.group(1))


def _textos_de_diagnostico(alvo) -> list[str]:
    """Lê texto para diagnóstico sem nunca levantar.

    O coletor roda dentro de um ``except`` — quando o teste já falhou — e página navegando é
    o estado que produz a falha. A leitura one-shot nesse instante levanta
    ``Error: Execution context was destroyed`` e **substitui** a ``AssertionError`` original,
    deixando o relatório sem a mensagem que dizia o que não aconteceu (#16990). Mesmo defeito
    corrigido em ``djtools/e2e_ui.py``.
    """
    try:
        return [texto.strip() for texto in alvo.all_inner_texts() if texto.strip()]
    except Exception as erro:
        return [f'<indisponível: {type(erro).__name__}>']


def mensagem_de_sucesso(page: Page, texto: str, timeout: int = TEMPO_ESPERA) -> None:
    """Afirma a mensagem de confirmação do SUAP após uma ação bem-sucedida.

    O banner é ``<p class="alert alert-{tag}" id="feedback_message">``
    (``djtools/templates/components/messages.html``). A ``tag`` vem do nível da mensagem
    Django e **não é uniforme**: o admin manda ``success``, mas ``httprr`` sem nível
    explícito manda ``info`` — o cadastro de curso, por exemplo, confirma em
    ``alert-info``. Por isso o âncora é o ``id``, com ``alert-error`` explicitamente
    excluído para a asserção não passar quando a ação falhou.

    Sempre afirme o fato POSITIVO. Ausência de mensagem de erro não é prova de sucesso —
    dependendo do timing do submit ela dá falso verde e falso vermelho.

    O timeout é maior que o padrão de 5s do ``expect`` porque vários saves do edu
    (curso, turma, fechamento de período) redirecionam depois de um processamento longo.
    """
    banner = page.locator('p#feedback_message:not(.alert-error):not(.alert-danger)', has_text=texto)
    try:
        expect(banner.first).to_be_visible(timeout=timeout)
    except AssertionError as falha:
        # Sem isto, o diagnóstico de "não apareceu" exige rodar de novo com o browser
        # aberto: a causa quase sempre é uma validação que está escrita na própria tela.
        feedback = _textos_de_diagnostico(page.locator('p#feedback_message'))
        erros = _textos_de_diagnostico(page.locator('p.errornote, ul.errorlist li'))
        raise AssertionError(f'mensagem de sucesso "{texto}" não apareceu. URL: {page.url} | feedback: {feedback} | erros: {erros}') from falha


def mensagem_de_erro(page: Page, texto: str, timeout: int = TEMPO_ESPERA) -> None:
    """Afirma um erro do SUAP, tanto o banner (``httprr`` com nível error) quanto o de form.

    Erro de validação de formulário sai em ``p.errornote``/``ul.errorlist``; erro de regra
    de negócio devolvido por ``httprr`` sai no mesmo banner do sucesso, com
    ``alert-error``.
    """
    erro = page.locator('p.errornote, ul.errorlist li, p#feedback_message.alert-error')
    expect(erro.filter(has_text=texto).first).to_be_visible(timeout=timeout)


@pytest.fixture
def _django_db_helper() -> None:
    """Anula o wrapper TestCase/TransactionTestCase do pytest-django nos e2e.

    O pytest-django força ``transaction=True`` quando ``live_server`` é pedido
    (``pytest_django/fixtures.py:237`` e ``:639``), e o teardown do
    ``TransactionTestCase`` dá flush em todas as tabelas
    (``django/test/testcases.py:1253``). Isso apagaria ``auth_group``,
    ``comum.GroupDetail`` e ``comum.GerenciamentoGrupo`` (que o ``post_migrate`` NÃO
    recria) e exigiria re-rodar ``sync_permissions`` a cada teste — "dezenas de
    segundos" segundo ``comum/pytest_fixtures.py:228``.

    O marker ``@pytest.mark.django_db(databases='__all__')`` continua obrigatório nos
    testes: é ele que faz ``django_db_setup`` calcular os aliases
    (``fixtures.py:183``) e criar o banco de teste. Sem marker, ``aliases`` fica vazio,
    ``DATABASES['default']['NAME']`` nunca é reescrito e o browser roda contra o banco
    de desenvolvimento.

    Acoplamento a nome privado do pytest-django: um rename futuro reativa o flush.
    Falha alto (seed apagado ⇒ tudo depois do 1º teste morre), então não há guard.
    """
    return


@pytest.fixture(scope='session', autouse=True)
def _exige_banco_de_e2e() -> None:
    """Falha alto se a run não estiver apontada para um banco de teste só de e2e.

    O seed do e2e (``initial_data``) e a fixture ``suap_data`` de
    ``comum/pytest_fixtures.py`` criam a mesma árvore organizacional de formas
    incompatíveis: compartilhar banco faz ``suap_data`` estourar ``UniqueViolation`` em
    ``unidadeorganizacional_setor_id_key``. Por isso o banco tem de ser separado.

    A separação vem de ``TEST_DATABASE_NAME`` (env), não de um override de
    ``django_db_modify_db_settings``: aquele override era session-scoped e, com os e2e
    espalhados por ``<modulo>/tests/e2e/``, ele passava a existir em vários conftests
    irmãos. Fixture session-scoped definida em conftests diferentes é instanciada **uma
    vez por conftest** (é o mesmo alerta da docstring de ``comum/pytest_fixtures.py``),
    então o sufixo era aplicado por subárvore e cada uma ia para um banco diferente — o
    seed ficava num, os testes liam o outro.
    """
    from django.conf import settings

    nome = settings.DATABASES['default'].get('TEST', {}).get('NAME') or ''
    assert '_e2e' in nome, (
        f'banco de teste {nome!r} não é de e2e. Rode com TEST_DATABASE_NAME=test_suap_e2e para não corromper o banco reusado da suíte unitária.'
    )


def _fechar_conexoes_orfas() -> None:
    """Derruba conexões remanescentes no banco de teste, antes do pytest-django dropá-lo.

    A thread do ``live_server`` (e as threads de request do WSGI) abrem conexão própria, e
    ``live_server.stop()`` não as fecha — ``connections.close_all()`` só alcança a thread
    atual. Medido: ao fim da sessão restava uma sessão ``idle`` cuja última query era um
    ``SELECT ... FROM rh_servidorfuncaohistorico``, isto é, uma request servida pelo
    servidor de teste. Resultado: ``DROP DATABASE`` falha com "is being accessed by other
    users", o pytest-django emite warning e o banco de teste fica órfão.

    Derrubar é seguro porque o banco está a um passo de ser destruído — e é o mesmo que o
    ``conftest.py`` raiz já faz antes de recriá-lo.
    """
    import psycopg
    from django.conf import settings
    from django.db import connections

    connections.close_all()

    config = settings.DATABASES['default']
    banco_de_teste = (config.get('TEST') or {}).get('NAME')
    if not banco_de_teste:
        return
    try:
        # Conecta no banco de manutenção (não no de teste), senão a própria conexão daqui
        # seguraria o drop.
        with psycopg.connect(
            host=config['HOST'],
            port=config['PORT'],
            user=config['USER'],
            password=config['PASSWORD'],
            dbname=os.environ.get('DATABASE_NAME', 'postgres'),
            autocommit=True,
        ) as conexao:
            conexao.execute(
                'SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()',
                (banco_de_teste,),
            )
    except Exception as erro:  # nunca deixa o teardown quebrar a sessão
        # stderr direto: o hook `prints` do pre-commit proíbe print() aqui, e o logging
        # está desabilitado pelo conftest raiz (`logging.disable(CRITICAL)`).
        sys.stderr.write(f'[e2e] não foi possível encerrar conexões de {banco_de_teste}: {erro}\n')


@pytest.fixture(scope='session')
def e2e_banco(_exige_banco_de_e2e: None, request: pytest.FixtureRequest, django_db_setup: None, django_db_blocker: DjangoDbBlocker) -> Iterator[None]:
    """Banco de teste aberto para a sessão inteira, com os settings do e2e pinados.

    É a moldura de todo seed: ``e2e_seed`` e os seeds de módulo dependem daqui e só gravam dados.

    ``_exige_banco_de_e2e`` é o PRIMEIRO parâmetro de propósito (#17654): o pytest monta os
    argumentos na ordem da assinatura, então o guard roda antes de ``django_db_setup`` criar
    o banco. Ser autouse não basta: o ``_verify_url`` do pytest-base-url é autouse de plugin,
    roda antes dos autouse de conftest e puxa ``base_url`` → ``live_server`` → ``e2e_seed``,
    ou seja, o seed já estaria commitado no banco errado quando o guard reclamasse.
    """
    with django_db_blocker.unblock():  # mantido aberto a sessão toda
        from django.conf import settings

        # LPS troca urls/templates/menus/permissões (suap/settings_base.py:741).
        # Pinar evita que o shell do dev mude o alvo do teste silenciosamente.
        settings.LPS = os.environ.get('LPS', '')

        # O que quebra os assets é o bundling do pipeline, e ele resolve
        # PIPELINE_ENABLED = not DEBUG no *import* (pipeline/conf.py:10) — logo depende do
        # módulo de settings, não do DEBUG em runtime (que o pytest-django força para
        # False em plugin.py:517 via a ini `django_debug_mode`). Ver o comentário em
        # suap/settings_test.py.
        from pipeline.conf import settings as pipeline_settings

        assert not pipeline_settings.PIPELINE_ENABLED, (
            'assets vão dar 404 e o JS não carrega: rode com DJANGO_SETTINGS_MODULE=suap.settings_test (DEBUG=True no módulo)'
        )
        # Restaura DEBUG em runtime só para não cair no handler 500 do SUAP, que rebenta
        # no StaticFilesHandler (request sem .user). Mesmo que as fixtures unitárias fazem.
        settings.DEBUG = True

        # O `.env` do checkout principal chega por `load_dotenv` e pode trazer chaves reais:
        # com elas o login exigiria o captcha.
        settings.RECAPTCHA_PUBLIC_KEY = ''
        settings.RECAPTCHA_PRIVATE_KEY = ''
        yield

    # Este fixture faz teardown depois do `live_server` (que depende dele via `e2e_seed`) e
    # antes do `django_db_setup` (de quem depende) — a única janela em que dá para limpar as
    # conexões sem atropelar quem ainda precisa do banco.
    if not request.config.getvalue('reuse_db'):
        _fechar_conexoes_orfas()


@pytest.fixture(scope='session')
def e2e_seed(e2e_banco):
    """Carga inicial única da sessão, commitada, nunca revertida: ``semear_base()`` (#17486).

    Catálogos, instituição, raiz e ``admin``. O módulo que precisa de mais (campi, servidores,
    domínio) monta o próprio seed de sessão dependendo desta fixture, com as factories dele.
    """
    semear_base()


def _carregar_catalogos() -> None:
    """Catálogos de referência: o ``manage.py sync`` de produção sem ``migrate``/``collectstatic``.

    Não é dado de teste — são as tabelas de domínio que produção também carrega (tipos de UO,
    situações, grupos e permissões...), por isso ficam como fixture/comando, não como factory.
    Roda antes de qualquer factory porque o ``loaddata`` grava por pk.
    """
    from django.conf import settings
    from django.core.management import call_command

    call_command('loaddata', 'initial_data', skip_checks=True, verbosity=0)
    for app in ('documento_eletronico', 'processo_eletronico'):
        if app in settings.INSTALLED_APPS_SUAP:
            call_command(f'{app}_initial', skip_checks=True, verbosity=0)
    call_command('sync_permissions', skip_checks=True, verbosity=0)
    call_command('carregar_apis', verbosity=0)


def _configurar_instituicao() -> None:
    from comum.models import Configuracao

    for chave, valor in (
        ('instituicao', 'Instituto Federal de Educação, Ciência e Tecnologia do Rio Grande do Norte'),
        ('instituicao_sigla', 'IFRN'),
        ('reitoria_sigla', SIGLA_RAIZ),
    ):
        Configuracao.objects.get_or_create(app='comum', chave=chave, valor=valor)


def _endereco() -> dict[str, object]:
    """Endereço de UO: telas que o imprimem (PAFC, documentos) leem ``municipio.nome`` sem guarda."""
    from comum.models import Municipio

    municipio = Municipio.objects.get_or_create(nome='Natal', uf='RN', defaults={'codigo': 'NAT'})[0]
    return {'endereco': 'Rua Dr. Nilo Bezerra Ramalho, 1692, Tirol', 'cep': '59015-300', 'municipio': municipio}


def _criar_raiz() -> Setor:
    """Setor raiz SUAP com a UO da reitoria (``tipo`` Reitoria, não campus).

    Reencontra a raiz pela sigla em vez de criar outra (duas raízes quebram ``Setor.raiz_suap``).
    """
    from rh.models import Setor, UnidadeOrganizacional
    from rh.tests.factories import SetorFactory, TipoUnidadeOrganizacionalFactory, UnidadeOrganizacionalFactory

    raiz = Setor.objects.filter(sigla=SIGLA_RAIZ, codigo=None).first()
    if raiz is None:
        raiz = SetorFactory(sigla=SIGLA_RAIZ, nome='Reitoria', campus=False)
        reitoria = TipoUnidadeOrganizacionalFactory(id=UnidadeOrganizacional.TIPO_REITORIA, descricao='Reitoria')
        UnidadeOrganizacionalFactory(setor=raiz, sigla=SIGLA_RAIZ, nome='Reitoria', codigo_ug=SIGLA_RAIZ, tipo=reitoria, **_endereco())
        raiz.refresh_from_db()
    return raiz


def setor(sigla: str, superior: Setor, nome: str | None = None, **campos: object) -> Setor:
    """Setor SUAP (``codigo`` nulo) sob ``superior``, herdando a ``uo`` dele. Idempotente pela sigla.

    Reencontra o setor SUAP de mesma sigla: módulos que dividem banco (job de doc) dividem a
    árvore. As siglas são as da árvore do antigo seed do behave (CEN, CZN, A0, DIAC/CEN...).
    ``campos`` (ex.: ``codigo_siorg``) valem também para o setor que já existia.
    """
    from rh.models import Setor
    from rh.tests.factories import SetorFactory

    existente = Setor.objects.filter(sigla=sigla, codigo=None).first()
    if existente is None:
        return SetorFactory(sigla=sigla, nome=nome or sigla, superior=superior, campus=False, **campos)
    if campos:
        Setor.objects.filter(pk=existente.pk).update(**campos)
        existente.refresh_from_db()
    return existente


def campus(sigla: str, nome: str | None = None, codigo_protocolo: str | None = None, **campos: object) -> Setor:
    """Campus: setor filho da raiz com UO própria de ``tipo`` campus (#17402). Idempotente pela sigla.

    ``codigo_protocolo`` vai para a UO (o prefixo do NUP dos processos) e ``campos`` para o setor
    (ex.: ``codigo_siorg``). Chame ANTES de criar os servidores do campus: ``User.get_vinculo``
    guarda o setor em ``User.VINCULOS``, cache de classe que o ``live_server`` herda, e um código
    gravado depois não chega lá.
    """
    from rh.models import UnidadeOrganizacional
    from rh.tests.factories import UnidadeOrganizacionalFactory

    setor_campus = setor(sigla, _criar_raiz(), nome, **campos)
    if not UnidadeOrganizacional.objects.filter(setor=setor_campus).exists():
        # UnidadeOrganizacional.save regrava todos os setores: é o que troca a `uo` herdada da raiz.
        extras = {'codigo_protocolo': codigo_protocolo} if codigo_protocolo else {}
        UnidadeOrganizacionalFactory(setor=setor_campus, sigla=sigla, nome=nome or sigla, **_endereco(), **extras)
        setor_campus.refresh_from_db()
    elif codigo_protocolo:
        UnidadeOrganizacional.objects.filter(setor=setor_campus).update(codigo_protocolo=codigo_protocolo)
        setor_campus.refresh_from_db()
    return setor_campus


def _email_pessoal(vinculo: Vinculo | None, email: str | None) -> None:
    """Grava o e-mail pessoal do vínculo: é para onde vão token de senha, código de 2FA e avisos."""
    from comum.models import Vinculo

    if vinculo is not None and email:
        Vinculo.objects.filter(pk=vinculo.pk).update(email_pessoal=email)


def servidor_com_login(
    matricula: str,
    setor: Setor,
    grupos: Iterable[str] = (),
    staff: bool = False,
    email_pessoal: str | None = None,
    **campos: object,
) -> Servidor:
    """Servidor (``ServidorFactory``) que loga com ``SENHA_E2E``; ``logado(matricula)`` já acha a senha.

    ``grupos`` são nomes de ``Group`` (os do ``sync_permissions``); ``staff`` abre o ``/admin/``;
    ``email_pessoal`` vai para o vínculo (troca de senha, autosserviço, 2FA e notificações o
    exigem). ``campos`` vão para a factory (ex.: ``pessoa_fisica__nome='Fulano'``). Não preenche
    ``setor_lotacao``: o módulo que precisa passa em ``campos``.
    """
    from django.contrib.auth.models import Group

    from rh.tests.factories import ServidorFactory

    # O `save` do servidor cria o `Papel` do cargo (o "Perfil" de assinatura) a partir desta data,
    # ou de "hoje" sem ela — e "hoje", sob o relógio congelado de um módulo, deixa o papel fora
    # das datas em que os testes rodam.
    campos.setdefault('data_inicio_exercicio_no_cargo', date(2010, 1, 1))
    servidor = ServidorFactory(matricula=matricula, setor=setor, **campos)
    if 'pessoa_fisica__nome' in campos:
        # A factory é get-or-create pela matrícula e ignora os campos de quem já existe: sem isto,
        # dois seeds no mesmo banco (doc + e2e do mesmo módulo) ficariam com o nome do primeiro.
        servidor.pessoa_fisica.nome = campos['pessoa_fisica__nome']
    usuario = servidor.get_user()
    usuario.set_password(SENHA_E2E)
    usuario.is_staff = usuario.is_staff or staff
    usuario.save()
    usuario.groups.add(*(Group.objects.get(name=nome) for nome in grupos))  # get: nome errado falha alto
    _email_pessoal(servidor.get_vinculo(), email_pessoal)
    # O `search_fields_optimized` da pessoa (que o autocomplete pesquisa) sai dos usernames dos
    # vínculos no `save` dela, e o usuário nasce depois da pessoa: sem este save, em banco frio o
    # autocomplete não acha o servidor pela matrícula (medido no seed do demandas).
    servidor.pessoa_fisica.save()
    return servidor


def aluno_com_login(
    matricula: str,
    setor: Setor,
    nome: str,
    codigo_curso: str,
    email_pessoal: str | None = None,
    ano_letivo: int = 2020,
    **campos: object,
) -> Aluno:
    """Aluno matriculado (grupo ``Aluno``, ``staff``) que loga com ``SENHA_E2E``. Idempotente pela matrícula.

    Monta o que o aluno exige para existir: a ``Diretoria`` em ``setor`` e um curso técnico de
    código **próprio do módulo** (``codigo_curso``) nessa diretoria — as views comparam a ``uo``
    do curso com a do programa/campus, e um ``TECINFO`` de outro módulo, no banco compartilhado
    do job de doc, pode ser de outro campus. ``campos`` vão para a ``AlunoFactory`` na criação
    (ex.: ``pessoa_fisica__cpf``).
    """
    from django.contrib.auth.models import Group

    from comum.tests.factories import AnoFactory
    from edu.models import Aluno, CursoCampus, Diretoria, Modalidade, NivelEnsino
    from edu.tests.factories import AlunoFactory

    diretoria = Diretoria.objects.filter(setor=setor).first() or Diretoria.objects.create(setor=setor)
    modalidade = Modalidade.objects.get_or_create(descricao='Técnico Integrado', defaults={'nivel_ensino_id': NivelEnsino.MEDIO})[0]
    curso = CursoCampus.objects.update_or_create(
        codigo=codigo_curso,
        defaults={'descricao': 'Técnico em Informática', 'diretoria': diretoria, 'ativo': True, 'modalidade': modalidade},
    )[0]
    # filter-first: o `save` de um aluno novo recusa matrícula que já tem `User` (rerun com --reuse-db).
    aluno = Aluno.objects.filter(matricula=matricula).first() or AlunoFactory(
        matricula=matricula,
        pessoa_fisica__nome=nome,
        pessoa_fisica__nascimento_data=date(2010, 1, 1),
        ano_letivo=AnoFactory(ano=ano_letivo),
        periodo_atual=1,
        curso_campus=curso,
        **campos,
    )
    aluno.pessoa_fisica.nome = nome
    _email_pessoal(aluno.get_vinculo(), email_pessoal)
    usuario = aluno.get_user()
    assert usuario is not None, f'o aluno {matricula} ficou sem usuário'
    usuario.set_password(SENHA_E2E)
    usuario.is_staff = True
    usuario.save()
    usuario.groups.add(Group.objects.get(name='Aluno'))
    # O vínculo nasce depois do `save` da pessoa no `Aluno.save`: sem este, o autocomplete não acha a matrícula.
    aluno.pessoa_fisica.save()
    return aluno


def criar_servidores(setor: Setor, servidores: Mapping[str, tuple[str, Iterable[str]]]) -> None:
    """``servidor_com_login`` em lote, com ``staff``: ``{matricula: (nome, grupos)}``, todos em ``setor``.

    É a tabela ``os seguintes usuários`` do behave (``step_seguintes_usuarios``) em factories.
    Idempotente: a ``ServidorFactory`` é get-or-create pela matrícula.
    """
    for matricula, (nome, grupos) in servidores.items():
        servidor_com_login(matricula, setor, grupos=grupos, staff=True, pessoa_fisica__nome=nome)


def semear_base() -> Setor:
    """Seed mínimo por factories, sem o behave: catálogos, instituição, raiz e o ``admin``.

    É o que TODA suíte precisa para logar e abrir telas; o resto (campi, setores, papéis) o
    conftest do módulo cria com as factories dele. Idempotente (``--reuse-db``, módulos que
    dividem banco): com o ``admin`` já semeado, não grava nada. Devolve a raiz.
    """
    from django.contrib.auth import get_user_model
    from django.core.cache import cache

    usuarios = get_user_model().objects
    # Sentinela no ÚLTIMO passo (o `admin` vira superusuário): seed interrompido refaz tudo.
    if not usuarios.filter(username='admin', is_superuser=True).exists():
        _carregar_catalogos()
        _configurar_instituicao()
        cache.clear()  # `Configuracao` é lida via cache
        servidor_com_login('admin', _criar_raiz())
        usuarios.filter(username='admin').update(is_superuser=True, is_staff=True)
    return _criar_raiz()


@pytest.fixture(scope='session')
def live_server(e2e_seed, live_server):
    """Garante a ordem seed → servidor.

    ``django_db_setup`` (via ``e2e_seed`` → ``e2e_banco``) reescreve ``DATABASES['default']['NAME']``;
    a thread do servidor não pode abrir conexão antes disso.
    """
    return live_server


@pytest.fixture(scope='session')
def base_url(live_server) -> str:
    """URL base do ``pytest-base-url``, para os testes usarem ``page.goto('/rota/')``."""
    return live_server.url


@pytest.fixture(scope='session')
def login_ui():
    """Devolve ``(page, matricula, senha=None) -> Page`` que autentica pela tela de login.

    Sem ``senha``, usa ``SENHA_E2E`` — a de todo usuário semeado.
    """

    def _login(page: Page, matricula: str, senha: str | None = None) -> Page:
        # Teto explícito: este é o pior caso de navegação da suíte — contexto novo, cache
        # vazio, primeiro login do papel. É o que estourou os 30s no `gerar-doc` do CI.
        page.goto('/accounts/login/', timeout=TEMPO_NAVEGACAO)
        page.fill('#id_username', matricula)
        page.fill('#id_password', senha or SENHA_E2E)
        # O #2fa-row sempre aparece sob testes (comum/views.py:3419 devolve 'OK'
        # quando running_tests()), mas auth_code é required=False — ignorar basta.
        page.click('input[type=submit][value="Acessar"]')
        # Mesma asserção de identidade do behave (common_steps/when.py:181).
        expect(page.locator(f'[title*="Vínculo: {matricula}"]').first).to_be_visible()
        # O crachá do vínculo aparece com o HTML da index, mas os quadros, as pendências e o
        # contador de notificações continuam em voo: medido, `jQuery.active == 7` neste ponto.
        # Quem devolve a página aqui a entrega meio carregada, e o teste seguinte corre contra
        # essas requisições — em `comum/tests/e2e/test_sessao_dispositivos.py` isso aparecia
        # como flake de 1 em 3 (o logout dava flush na sessão e uma requisição em voo a
        # regravava, devolvendo o usuário autenticado à index). Esperar o jQuery parar é o
        # mesmo gesto de `Tela.esperar`, e vale para toda suíte que começa logo após o login.
        try:
            page.wait_for_function('() => !window.jQuery || jQuery.active === 0', timeout=TEMPO_ESPERA)
        except Exception:
            # Igual a `Tela.esperar`: um widget que faz polling eterno não pode reprovar o login.
            pass
        return page

    return _login


@pytest.fixture(scope='session')
def storage_states(browser, base_url, login_ui):
    """Devolve ``(matricula) -> storage_state``, com UM login real por papel na sessão.

    Testes que fazem logout (ou que testam o próprio login) NÃO podem usar isto: o
    logout invalida a sessão daquele papel no servidor para todos os testes seguintes.
    """
    cache: dict[str, dict] = {}

    def _get(matricula: str, senha: str | None = None) -> dict:
        if matricula not in cache:
            contexto = browser.new_context(base_url=base_url)
            try:
                login_ui(contexto.new_page(), matricula, senha)
                cache[matricula] = contexto.storage_state()
            finally:
                contexto.close()
        return cache[matricula]

    return _get


@pytest.fixture
def logado(new_context, storage_states):
    """Devolve ``(matricula) -> Page``: contexto novo por teste, já autenticado.

    ``new_context`` é do pytest-playwright: honra ``--tracing``/``--video`` e fecha
    sozinho no fim do teste.
    """

    def _logado(matricula: str, senha: str | None = None) -> Page:
        # base_url NÃO vai aqui: o new_context do pytest-playwright já espalha
        # browser_context_args, que o consome da fixture base_url.
        contexto = new_context(storage_state=storage_states(matricula, senha))
        page = contexto.new_page()
        page.on('dialog', lambda dialog: dialog.accept())
        return page

    return _logado
