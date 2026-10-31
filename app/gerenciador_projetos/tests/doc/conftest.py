"""Substrato da rodada de geração da doc de usuário do ``gerenciador_projetos``.

Esta suíte NÃO é de regressão: ela navega o sistema vivo para *descobrir* o que a doc de
usuário vai afirmar e para capturar as telas. Cada teste é o roteiro de uma tarefa; a
asserção existe só para a rodada falhar alto quando a tela mudou de forma — doc que
descreve um passo inexistente é pior que doc velha.

O módulo **não tem** ``tests/e2e/`` nem ``features/`` (nenhuma `.feature` do behave o
cobre), então não há substrato para reusar: o seed inteiro nasce aqui, e as tarefas da doc
foram **propostas** a partir de ``menu.yaml`` + ``admin.py`` + ``views.py`` — não colhidas
do inventário. Só o star-import de ``djtools.e2e_fixtures`` é herdado — obrigatório em
conftest, porque é a precedência de conftest sobre plugin que faz os overrides privados
(``_django_db_helper``, ``_exige_banco_de_e2e``) valerem.

Decisões deste módulo:

1. **Papéis** — três, e são os grupos de ``permissions.yaml``: ``gerente`` (cria o projeto
   e o organiza), ``membro`` (cria e executa tarefas), ``interessado`` (acompanha, só
   leitura). Criados eager e session-scoped pelo cache de permissão por processo.

2. **Autorização é por linha, não só por grupo.** O grupo dá a permissão de tela
   (``view_projeto`` etc.), mas as views do módulo checam **equipe do projeto**
   (``Projeto.pode_ver_projeto``/``pode_editar_projeto``/``pode_adicionar_tarefas``) — um
   usuário com o grupo fora da equipe leva 403 na página do projeto. Por isso o "Quem pode"
   das tarefas na doc foi escrito à mão (a equipe manda tanto quanto o grupo).

3. **Grupos concedidos pela equipe.** ``m2m_changed`` em ``Projeto.gerentes/membros/
   interessados`` põe no grupo do módulo quem é incluído na equipe de qualquer projeto. A
   doc afirma isso, e a afirmação é EXECUTADA: ``membro`` e ``interessado`` nascem só com o
   grupo ``Servidor`` e o teste 1 confere que ganharam o grupo ao entrar na equipe. Isso não
   esbarra no cache de permissão por processo porque nenhum dos dois loga antes do teste 1
   (o login de cada papel é preguiçoso, em ``storage_states``). O ``gerente`` precisa do
   grupo de saída — é ele quem cria o primeiro projeto.

4. **Tabelas de apoio** — o seed base (``semear_base``) não instala nada do módulo, e duas
   tabelas são pré-requisito de formulário que abre: ``comum.AreaAtuacao`` (o cadastro de
   projeto exige ao menos uma) e ``TipoAtividade`` (o campo é obrigatório no formulário de
   tarefa). Ambas semeadas por ORM — são as "telas de apoio" que a doc lista sem documentar.
   O segundo campus (``CEN``) existe só para a tarefa "Distribuir uma tarefa entre campi":
   com um campus só, a tela não tem o que distribuir.

5. **Encadeamento** — os testes formam uma cadeia: o projeto nasce pela UI no teste 1, e os
   demais o reencontram pela fixture ``projeto_da_rodada``, que ancora no **gerente**
   (matrícula ``1580001``, exclusiva desta suíte) e não no título. O CI roda ``pytest -m
   doc`` inteiro num banco só, compartilhado entre módulos e sem flush entre testes, então a
   colisão de nomes é resolvida ancorando em chave própria — nunca marcando o título, que é
   o que aparece nas capturas. Pelo mesmo motivo, quem procura tarefa por nome filtra também
   por ``projeto``. O clone do último teste (``Cópia de …``) tem o mesmo gerente e pk maior,
   por isso a âncora o exclui.

6. **Substrato dos testes unitários anulado aqui.** ``gerenciador_projetos/tests/conftest.py``
   tem um ``substrato_gerenciador`` autouse que pede ``sync_permissions`` — e esse fixture
   força ``DEBUG=True`` por classe (``comum/pytest_fixtures.py``), por cima do ``DEBUG=False``
   que o ``capturar`` liga. Medido em 07/10/2026: com ele, toda captura saía com a barra
   ``#debug`` (caminho do projeto e banco) e o tema vinho de desenvolvimento. O override por
   nome abaixo tira o autouse desta pasta sem tocar nos testes unitários.

Rodar::

    DATABASE_HOST=localhost DATABASE_PORT=5434 DATABASE_USER=postgres DATABASE_PASSWORD=postgres \\
        TEST_DATABASE_NAME=test_suap_doc_e2e DJANGO_SETTINGS_MODULE=suap.settings_test \\
        uv run pytest -m doc --create-db gerenciador_projetos/tests/doc/

``--create-db``, não ``--reuse-db``: banco novo é a condição do CI (o job ``gerar-doc``
roda ``pytest -m doc`` sobre o serviço recém-subido). Em banco reusado a suíte ainda
funciona — a âncora pega o projeto mais recente do gerente —, mas os projetos das rodadas
anteriores continuam lá, e é a listagem de projetos que a primeira captura mostra.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from django.conf import settings

from djtools.e2e_fixtures import *  # noqa: F403
from djtools.e2e_fixtures import campus, criar_servidores
from gerenciador_projetos.models import Projeto  # usado na anotação de `projeto_da_rodada`

DESTINO = Path(settings.BASE_DIR) / 'gerenciador_projetos' / 'docs' / 'usuario'

# A fixture `capturar` é compartilhada (`djtools/e2e_fixtures.py`): viewport, teto do WebP e
# limpeza do destino são os mesmos em todo módulo — só o destino muda.
capturar = capturas(DESTINO)  # noqa: F405

# Apelido -> matrícula. Faixa 15800xx livre das outras suítes de doc.
PAPEIS = {'gerente': '1580001', 'membro': '1580002', 'interessado': '1580003'}

# Matrícula -> (nome, grupos); os três no campus CZN. Membro e interessado SEM o grupo do
# módulo: quem o concede é a inclusão na equipe (decisão 3 da docstring).
SERVIDORES = {
    '1580001': ('Gerente Projeto Doc', ['Servidor', 'Gerente de Projeto']),
    '1580002': ('Membro Projeto Doc', ['Servidor']),
    '1580003': ('Interessado Projeto Doc', ['Servidor']),
}

# Tabelas de apoio semeadas por ORM (a doc as lista, não as documenta).
AREA_ATUACAO = 'Tecnologia da Informação'
TIPO_ATIVIDADE = 'Planejamento'


@pytest.fixture
def substrato_gerenciador() -> None:
    """Anula, nesta pasta, o autouse homônimo de ``gerenciador_projetos/tests/conftest.py``.

    Aquele é substrato de teste unitário (superusuário por classe) e puxa ``sync_permissions``,
    que liga ``DEBUG=True`` e estragava as capturas — ver a decisão 6 da docstring do módulo.
    """
    return None


@pytest.fixture(scope='session')
def doc_seed(e2e_seed) -> None:
    """Os três servidores, o segundo campus e as tabelas de apoio, antes da primeira request.

    Session-scoped e eager por causa do cache de permissão por processo: usuário que ganha
    grupo depois do primeiro login continua sem acesso. Tudo é idempotente
    (``get_or_create``), o que é obrigatório porque o banco é compartilhado entre os
    módulos da rodada e não há flush entre eles.
    """
    from comum.models import AreaAtuacao

    from gerenciador_projetos.models import TipoAtividade

    criar_servidores(campus('CZN', 'Campus Zona Norte'), SERVIDORES)
    campus('CEN', 'Campus Central')
    AreaAtuacao.objects.get_or_create(nome=AREA_ATUACAO)
    TipoAtividade.objects.get_or_create(nome=TIPO_ATIVIDADE)


@pytest.fixture(scope='session')
def servidores_doc(doc_seed) -> dict:
    """``{apelido: Servidor}`` dos papéis de ``PAPEIS``."""
    from rh.models import Servidor

    return {papel: Servidor.objects.get(matricula=matricula) for papel, matricula in PAPEIS.items()}


@pytest.fixture
def logado_doc(logado, doc_seed):
    """``(papel) -> Page`` autenticada como o servidor daquele papel de ``PAPEIS``."""

    def _logado(papel: str):
        assert papel in PAPEIS, f'papel desconhecido: {papel}; declare em PAPEIS'
        return logado(PAPEIS[papel])

    return _logado


@pytest.fixture
def projeto_da_rodada(doc_seed) -> Projeto:
    """O projeto que o teste 1 criou pela UI — a âncora da cadeia de testes.

    Ancorado no **gerente** da rodada, não no título: os nomes entram nas capturas, e um
    sufixo de unicidade no título vazava para dentro da doc. A matrícula ``1580001`` é
    exclusiva desta suíte (faixa reservada em ``PAPEIS``), então o projeto mais recente
    desse gerente é sempre o desta rodada, mesmo em banco reusado — descontado o clone que
    o último teste cria, que tem o mesmo gerente.
    """
    from gerenciador_projetos.models import Projeto

    return Projeto.objects.filter(gerentes__username=PAPEIS['gerente']).exclude(titulo__startswith='Cópia de ').order_by('-pk').first()
