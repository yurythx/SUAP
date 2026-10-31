"""Substrato da rodada de geração da doc de usuário do ``projetos_ensino``.

Esta suíte NÃO é de regressão: ela navega o sistema vivo para *descobrir* o que a doc de
usuário vai afirmar e para capturar as telas. Cada teste é um roteiro de tarefa; a asserção
existe só para a rodada falhar alto quando a tela mudou de forma.

Como o módulo não tem ``tests/e2e/`` (diferente do ``eventos``), o substrato é montado aqui
mesmo: star-import de ``djtools.e2e_fixtures`` (obrigatório e primeiro — traz os nomes
**privados** ``_django_db_helper``/``_exige_banco_de_e2e``), ``e2e_seed`` por factories
(#17486: só ``semear_base``) e, no ``doc_seed``, o campus CZN, os papéis
(``criar_servidores`` + o aluno), o step do behave do próprio módulo
(``projetos_ensino/features/steps/given.py`` — só ``get_or_create`` sobre nomenclatura:
financeiro, tipos, eixos, anos) e a origem de recurso.

O conftest dos testes de fluxo unitário (``projetos_ensino/tests/conftest.py``) NÃO é
importado de propósito: os payloads de lá foram lidos apenas para saber quais campos
existem. O motivo original era que as fixtures dele dependiam de ``suap_data``, incompatível
com o seed e2e no mesmo banco (ver ``djtools/e2e_fixtures.py``); desde a migração delas para
factories esse impedimento não existe mais, mas a separação foi mantida — unificar os dois
seeds não foi testado.

Rodar::

    DATABASE_HOST=127.0.0.1 DATABASE_PORT=5432 DATABASE_USER=postgres DATABASE_PASSWORD=postgres \
      TEST_DATABASE_NAME=test_suap_doc_e2e_projetos_ensino DJANGO_SETTINGS_MODULE=suap.settings_test \
      .venv/bin/python -m pytest -m doc --create-db projetos_ensino/tests/doc/ -q

``--create-db``, não ``--reuse-db``: banco novo é a condição do CI e esta suíte não é
perfeitamente idempotente entre execuções (os testes são independentes entre si por nome
único ``uuid4``, mas o total de linhas não é zero).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from django.conf import settings

from djtools.e2e_fixtures import *  # noqa: F403
from djtools.e2e_fixtures import aluno_com_login, campus, criar_servidores, setor

DESTINO = Path(settings.BASE_DIR) / 'projetos_ensino' / 'docs' / 'usuario'

# A fixture `capturar` é compartilhada (`djtools/e2e_fixtures.py`): viewport, teto do WebP e
# limpeza do destino são os mesmos em todo módulo — só o destino muda.
capturar = capturas(DESTINO)  # noqa: F405

# Apelido -> matrícula. Faixa 158xxx, própria deste módulo (o CI roda `pytest -m doc`
# inteiro num banco só; `eventos` usa 1550xx e os irmãos outras faixas).
PAPEIS = {
    'gerente': '158001',  # Gerente Sistêmico de Projetos de Ensino
    'coordenador': '158002',  # Coordenador de Projetos de Ensino (pré-seleção e monitoramento)
    'coordenador_projeto': '158003',  # Servidor → coordenador do projeto submetido
    'membro': '158004',  # Servidor → membro da equipe
    'avaliador_a': '158005',  # Avaliador de Projetos de Ensino
    'avaliador_b': '158006',
    'aluno': '2020010115807',  # Aluno → membro da equipe
}

# Matrícula -> (nome, grupos); todos no campus CZN.
SERVIDORES = {
    PAPEIS['gerente']: ('Gerente Proj Ensino Doc', ['Gerente Sistêmico de Projetos de Ensino']),
    PAPEIS['coordenador']: ('Coord Proj Ensino Doc', ['Coordenador de Projetos de Ensino']),
    PAPEIS['coordenador_projeto']: ('Coord Projeto Doc', ['Servidor']),
    PAPEIS['membro']: ('Membro Equipe Doc', ['Servidor']),
    PAPEIS['avaliador_a']: ('Avaliador Proj Doc A', ['Avaliador de Projetos de Ensino', 'Servidor']),
    PAPEIS['avaliador_b']: ('Avaliador Proj Doc B', ['Avaliador de Projetos de Ensino', 'Servidor']),
}


def _criar_aluno(setor_campus) -> None:
    """Aluno matriculado num curso da diretoria do campus CZN, como fazia o step do behave."""
    aluno_com_login(PAPEIS['aluno'], setor_campus, 'Aluno Proj Doc', 'TECINFO-PROJENS-DOC', email_pessoal='aluno_proj_doc_secundario@gmail.com')


@pytest.fixture(scope='session')
def doc_seed(e2e_seed):
    """Campus CZN (e a DIAC/CZN) + os sete papéis deste módulo + nomenclatura, antes da 1ª request.

    Session-scoped e eager pelo mesmo motivo do conftest do ``eventos``: o cache de
    permissão é por processo, então um usuário que ganha grupo depois do primeiro login
    continua sem acesso.
    """
    from projetos_ensino.features.steps import given as given_modulo
    from projetos_ensino.models import OrigemRecursoEdital

    czn = campus('CZN', 'Campus Zona Norte')
    # Setor que a submissão escolhe no select encadeado ao campus (test_02a).
    setor('DIAC/CZN', czn, 'Diretoria Acadêmica')
    criar_servidores(czn, SERVIDORES)
    _criar_aluno(czn)
    given_modulo.step_dados_basicos_projetos_ensino(None)
    # O formulário de fonte de recurso (`RecursoForm`) lista ``OrigemRecursoEdital`` ativas
    # (`projetos_ensino/forms.py:203`) e o step do behave não cria essa tabela de apoio.
    OrigemRecursoEdital.objects.get_or_create(descricao='CAMPUS', defaults={'ativo': True})


@pytest.fixture
def logado_doc(logado, doc_seed):
    """``(papel) -> Page`` autenticada como o usuário daquele papel de ``PAPEIS``."""

    def _logado(papel: str):
        assert papel in PAPEIS, f'papel desconhecido: {papel}; declare em PAPEIS'
        return logado(PAPEIS[papel])

    return _logado
