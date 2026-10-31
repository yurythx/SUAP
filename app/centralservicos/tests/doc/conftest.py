"""Substrato da rodada de geração da doc de usuário do ``centralservicos``.

Esta suíte NÃO é de regressão: ela navega o sistema vivo para *descobrir* o que a doc de
usuário vai afirmar e para capturar as telas. Cada teste é o roteiro de uma tarefa; a asserção
existe só para a rodada falhar alto quando a tela mudou de forma (senão a doc sairia
descrevendo um passo que já não existe).

O seed e as fixtures de estado vivem aqui (este conftest não importa o do ``tests/e2e/``):
star-import de ``djtools.e2e_fixtures`` (obrigatório e primeiro — traz os nomes privados
``_django_db_helper``/``_exige_banco_de_e2e``) + seed por factories (#17486): ``e2e_seed`` é só
a base (``semear_base``) e os papéis nascem em ``doc_seed`` via ``criar_servidores``, no setor
``DIAC/CZN`` do campus ``CZN`` (as siglas da antiga árvore do behave, que a doc cita).

**Os cadastros de domínio são criados pelos PRÓPRIOS testes, na ordem da doc** (área →
centros/grupos de atendimento → catálogo → Base de Conhecimento → chamados): o roteiro da doc
é uma cadeia e o seed de domínio fica vazio de propósito, para que a tela documentada seja a
mesma que produziu o dado usado adiante. O que o seed de sessão garante são só os papéis —
grupo de cada usuário, criado antes da primeira request porque o cache de permissão é por
processo (usuário que ganha grupo depois do primeiro login continua sem acesso).

Papéis (todos por grupo concedido no seed, via ``criar_servidores``):

- ``solicitante``/``colega``: grupo ``Servidor`` — abrem e acompanham chamados.
- ``atendente``: ``Servidor, Atendente da Central de Serviços`` — atende, resolve, suspende.
- ``responsavel``: os mesmos grupos do atendente, e é *responsável* pelos grupos de atendimento
  criados na tarefa 2 — é o papel que enxerga "Atribuir", "Escalar" e "Retornar" no chamado.
- ``gestor``: ``Servidor, Gestor da Central de Serviços`` + ``GestorAreaServico`` da área
  criada na tarefa 1 (o vínculo concede o grupo por signal; declarado no seed para o grupo
  existir antes do primeiro login) — mantém o catálogo, a estrutura e as tarefas.
- ``admin``: ``Servidor, centralservicos Administrador`` — cria a Área de Atuação no admin do
  ``comum`` (nenhum outro perfil padrão tem ``comum.add_areaatuacao``).
- ``contribuinte``: ``Servidor, Contribuinte da Base de Conhecimento`` — escreve artigo que
  **não** tem ``add_active_baseconhecimento``, logo nasce pendente de supervisão.
- ``supervisor``: ``Servidor, Supervisor da Base de Conhecimento`` — revisa e aprova o artigo.

Rodar::

    DATABASE_HOST=127.0.0.1 DATABASE_PORT=5432 DATABASE_USER=postgres DATABASE_PASSWORD=postgres \\
        TEST_DATABASE_NAME=test_suap_doc_e2e DJANGO_SETTINGS_MODULE=suap.settings_test \\
        uv run pytest -m doc centralservicos/tests/doc/

``--create-db`` na primeira vez; ``--reuse-db`` nas seguintes. A suíte é idempotente dentro de
uma sessão (os cadastros são recriados do zero no início de cada teste que os cria), mas o
banco é o mesmo das outras suítes de doc no CI (``pytest -m doc`` inteiro, um worker): as
asserções filtram por chave própria e medem delta, nunca contagem global.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from django.conf import settings

if TYPE_CHECKING:
    from comum.models import AreaAtuacao
    from django.contrib.auth.models import User

    from centralservicos.models import BaseConhecimento, CentroAtendimento, Chamado, GrupoAtendimento, Servico

from djtools.e2e_fixtures import *  # noqa: F403
from djtools.e2e_fixtures import campus, capturas, criar_servidores, setor

DESTINO = Path(settings.BASE_DIR) / 'centralservicos' / 'docs' / 'usuario'

# A fixture `capturar` é compartilhada (`djtools/e2e_fixtures.py`): viewport, teto do WebP e
# limpeza do destino são os mesmos em todo módulo — só o destino muda.
capturar = capturas(DESTINO)

PAPEIS = {
    'solicitante': '161101',
    'atendente': '161102',
    'responsavel': '161103',
    'gestor': '161104',
    'admin': '161105',
    'supervisor': '161106',
    'colega': '161107',
    'contribuinte': '161108',
}

# Matrícula -> (nome, grupos): a antiga tabela `os seguintes usuários` da doc.
SERVIDORES = {
    '161101': ('Solicitante Central Doc', ['Servidor']),
    '161102': ('Atendente Central Doc', ['Servidor', 'Atendente da Central de Serviços']),
    '161103': ('Responsavel Central Doc', ['Servidor', 'Atendente da Central de Serviços']),
    '161104': ('Gestor Central Doc', ['Servidor', 'Gestor da Central de Serviços']),
    '161105': ('Administrador Central Doc', ['Servidor', 'centralservicos Administrador']),
    '161106': ('Supervisor Central Doc', ['Servidor', 'Supervisor da Base de Conhecimento', 'Atendente da Central de Serviços']),
    '161107': ('Colega Central Doc', ['Servidor']),
    '161108': ('Contribuinte Central Doc', ['Servidor', 'Contribuinte da Base de Conhecimento', 'Atendente da Central de Serviços']),
}

# Nomes de domínio usados pelos testes e pela doc. O sufixo da área não é decorativo: o CI roda
# `pytest -m doc` inteiro num banco só, a Área de Atuação tem `nome` único e o módulo
# ``gerenciador_projetos`` semeia uma 'Tecnologia da Informação' — sem o sufixo, o delete do
# teste 1 apagaria a área dele e o `get_or_create` dele reusaria a minha.
AREA = 'Tecnologia da Informação (Central de Serviços)'
CENTRO_LOCAL = 'Local'
CENTRO_SISTEMICO = 'Sistêmico'
GRUPO_SISTEMICO = 'Suporte Sistêmico'
GRUPO_LOCAL = 'Suporte Local'
CATEGORIA = 'Impressão'
GRUPO_SERVICO = 'Impressora / Scanner'
SERVICO = 'Informar problema de Impressora/Scanner'
ARTIGO = 'Atolamento de papel na impressora'
ARTIGO_PUBLICO = 'Como digitalizar documentos no scanner'
TAREFA = 'Verificar a impressora'
SERVICO_TAREFA = 'Solicitar instalação de software'
CATEGORIA_SISTEMAS = 'Sistemas'
GRUPO_SERVICO_SISTEMAS = 'Sistemas Corporativos'


@pytest.fixture(scope='session')
def doc_seed(e2e_seed):
    """``e2e_seed`` + os usuários da doc, criados antes da primeira request.

    Session-scoped e eager pelo mesmo motivo do conftest do e2e: o cache de permissão é por
    processo, então um usuário que ganha grupo depois do primeiro login continua sem acesso.
    """
    criar_servidores(setor('DIAC/CZN', campus('CZN', 'Campus Zona Norte'), 'Diretoria Acadêmica'), SERVIDORES)


@pytest.fixture
def logado_doc(logado, doc_seed):
    """``(papel) -> Page`` autenticada, aceitando só os papéis declarados em ``PAPEIS``."""

    def _logado(papel: str):
        assert papel in PAPEIS, f'papel desconhecido: {papel}; declare em PAPEIS'
        return logado(PAPEIS[papel])

    return _logado


@pytest.fixture
def usuarios_doc(doc_seed):
    """``(papel) -> User``, para os testes ligarem os registros aos usuários do seed."""
    from django.contrib.auth import get_user_model

    User = get_user_model()

    def _usuario(papel: str) -> User:
        return User.objects.get(username=PAPEIS[papel])

    return _usuario


# ---------------------------------------------------------------------------------------------
# Leitura dos registros que os testes anteriores criaram — cada teste da cadeia depende do
# anterior, e o ``assert`` com mensagem diz qual rodar antes quando a cadeia quebrou.
# ---------------------------------------------------------------------------------------------


def area() -> AreaAtuacao:
    from comum.models import AreaAtuacao

    objeto = AreaAtuacao.objects.filter(nome=AREA).first()
    assert objeto is not None, f'área {AREA!r} ausente: rode test_cadastrar_area_e_gestor antes'
    return objeto


def servico() -> Servico:
    from centralservicos.models import Servico

    objeto = Servico.objects.filter(nome=SERVICO).first()
    assert objeto is not None, f'serviço {SERVICO!r} ausente: rode test_cadastrar_servico antes'
    return objeto


def grupo_local() -> GrupoAtendimento:
    from centralservicos.models import GrupoAtendimento

    objeto = GrupoAtendimento.objects.filter(nome=GRUPO_LOCAL).first()
    assert objeto is not None, f'grupo {GRUPO_LOCAL!r} ausente: rode test_cadastrar_estrutura_de_atendimento antes'
    return objeto


def centro_local() -> CentroAtendimento:
    from centralservicos.models import CentroAtendimento

    objeto = CentroAtendimento.objects.filter(nome=CENTRO_LOCAL, area=area()).first()
    assert objeto is not None, f'centro {CENTRO_LOCAL!r} ausente: rode test_cadastrar_estrutura_de_atendimento antes'
    return objeto


def artigo() -> BaseConhecimento:
    from centralservicos.models import BaseConhecimento

    objeto = BaseConhecimento.objects.filter(titulo=ARTIGO).first()
    assert objeto is not None, f'artigo {ARTIGO!r} ausente: rode test_escrever_e_aprovar_artigo antes'
    return objeto


def chamado_do_solicitante() -> Chamado:
    """O chamado mais recente aberto pelo solicitante no serviço da doc."""
    from centralservicos.models import Chamado

    objeto = Chamado.objects.filter(servico__nome=SERVICO, aberto_por__username=PAPEIS['solicitante']).order_by('-id').first()
    assert objeto is not None, 'chamado do solicitante ausente: rode test_abrir_chamado antes'
    return objeto
