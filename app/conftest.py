import logging
import os
import sys
import warnings
from unittest import mock

import django
import pytest
from django.conf import settings

logger = logging.getLogger(__name__)

pytest_plugins = ('comum.pytest_fixtures',)


@pytest.fixture(autouse=True)
def _limpar_threadlocals():
    """Limpa o usuário e a requisição que o middleware ``ThreadLocals`` deixa no processo.

    O middleware grava ``request.user`` e nunca limpa, e o ``CurrentUserField`` usa esse valor
    como default. Um teste que faz login com usuário criado na própria transação deixava o id
    para o próximo teste do mesmo worker, que gravava a FK de um usuário já desfeito no rollback
    (``movimentopatrim_usuario_id`` estourando no teardown). Como o ``--dist load`` do xdist monta
    os lotes pelo total de testes, a colisão aparecia ou sumia conforme a quantidade de testes.
    """
    yield
    from djtools.middleware import threadlocals

    threadlocals.context.__dict__.clear()


@pytest.fixture
def sem_unicidade_pessoa(db: None) -> None:
    """Remove, dentro da transação do teste, a unicidade, a obrigatoriedade de documento e as CHECK (como
    `pessoa_fisica_sem_cpf_exige_pais`) da PessoaFisica e a unicidade da PessoaInfoComplementar.

    Monta duplicatas como as da base legada; vale antes e depois da Release 2 (a DDL é desfeita no
    rollback do teste).
    """
    from django.db import connection

    from rh.models import PessoaFisica, PessoaInfoComplementar

    with connection.cursor() as cursor:
        for tabela in (PessoaFisica._meta.db_table, PessoaInfoComplementar._meta.db_table):
            cursor.execute("SELECT conname FROM pg_constraint WHERE conrelid = %s::regclass AND contype = 'u'", [tabela])
            for (nome,) in cursor.fetchall():
                cursor.execute(f'ALTER TABLE {tabela} DROP CONSTRAINT {connection.ops.quote_name(nome)}')
        cursor.execute("SELECT conname FROM pg_constraint WHERE conrelid = %s::regclass AND contype = 'c'", [PessoaFisica._meta.db_table])
        for (nome,) in cursor.fetchall():
            cursor.execute(f'ALTER TABLE {PessoaFisica._meta.db_table} DROP CONSTRAINT {connection.ops.quote_name(nome)}')
        cursor.execute(f'ALTER TABLE {PessoaFisica._meta.db_table} ALTER COLUMN documento_identificador DROP NOT NULL')


def mock_decorator_factory(*args, **kwargs):
    def noop_decorator(f):
        return f

    return noop_decorator


def _patched_execute_create_test_db(self, cursor, parameters, keepdb=False):
    dbname_sql = parameters['dbname']
    dbname_value = dbname_sql.strip('"').strip("'")

    if self._database_exists(cursor, parameters['dbname']):
        if not keepdb:
            cursor.execute(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = %s AND pid <> pg_backend_pid()
                """,
                [dbname_value],
            )
            cursor.execute(f'DROP DATABASE {dbname_sql}')
            cursor.execute(f'CREATE DATABASE {dbname_sql} {parameters["suffix"]}')
    else:
        cursor.execute(f'CREATE DATABASE {dbname_sql} {parameters["suffix"]}')

    test_db_name = dbname_value

    old_db_name = self.connection.settings_dict['NAME']
    self.connection.close()
    self.connection.settings_dict['NAME'] = test_db_name
    try:
        with self.connection.cursor() as test_cursor:
            test_cursor.execute('CREATE EXTENSION IF NOT EXISTS unaccent;')
            try:
                test_cursor.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm;')
            except Exception as exc:
                sys.stderr.write(
                    f'\n[ERRO EXTENSÃO POSTGRES] Falha ao criar extensão pg_trgm no banco {test_db_name}: {exc}\n'
                    'Verifique se o pacote postgresql-contrib está instalado no PostgreSQL ou use a imagem postgres:18 do AGENTS.md.\n'
                )
                raise
            try:
                test_cursor.execute('CREATE EXTENSION IF NOT EXISTS pg_stat_statements;')
            except Exception as exc:
                sys.stderr.write(
                    f'Extensão pg_stat_statements não criada (requer shared_preload_libraries): {exc}',
                )
            test_cursor.execute("""
                CREATE COLLATION IF NOT EXISTS ignore_accents_case (
                    provider = 'icu',
                    locale = 'pt-BR-u-ks-level1',
                    deterministic = false
                );
            """)
            test_cursor.execute("""
                CREATE OR REPLACE FUNCTION f_unaccent(text)
                    RETURNS text AS
                $func$
                SELECT unaccent('unaccent', upper($1))
                $func$  LANGUAGE sql IMMUTABLE SET search_path = public, pg_temp;
            """)
    finally:
        self.connection.close()
        self.connection.settings_dict['NAME'] = old_db_name


def pytest_configure(config):
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'suap.settings')
    os.environ['USUARIOGRUPO_AS_ABSTRACT'] = '1'
    os.environ['USE_EDU_LOG'] = 'False'
    django.setup()
    settings.USE_EDU_LOG = False

    from django.db.backends.postgresql.creation import DatabaseCreation

    # Na classe, não na instância: as conexões do Django são locais por thread/contexto, e a que cria o
    # banco de teste pode não ser a que existia aqui (ex.: e2e com pytest-playwright 0.10 + pytest-asyncio).
    # Sem o patch, o banco nasce sem pg_trgm e o índice gin_trgm_ops de Vinculo quebra (#17853).
    DatabaseCreation._execute_create_test_db = _patched_execute_create_test_db

    patcher = mock.patch(
        'oauth2_provider.decorators.protected_resource',
        side_effect=mock_decorator_factory,
    )
    patcher.start()
    config._suap_oauth_patcher = patcher

    logging.disable(logging.CRITICAL)

    warnings.filterwarnings(
        'ignore', message='cannot collect test class .* because it has a __init__ constructor', category=pytest.PytestCollectionWarning
    )


def pytest_unconfigure(config):
    patcher = getattr(config, '_suap_oauth_patcher', None)
    if patcher:
        patcher.stop()
    logging.disable(logging.NOTSET)


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    passed = len(terminalreporter.stats.get('passed', []))
    failed = len(terminalreporter.stats.get('failed', []))
    errors = len(terminalreporter.stats.get('error', []))
    skipped = len(terminalreporter.stats.get('skipped', []))
    total = passed + failed + errors + skipped

    terminalreporter.write_sep('=', 'SUAP test resume')
    terminalreporter.write_line(f'Total: {total}  Passed: {passed}  Failed: {failed}  Errors: {errors}  Skipped: {skipped}')

    if terminalreporter.stats.get('failed', []):
        terminalreporter.write_line('Failed tests:')
        for report in terminalreporter.stats.get('failed', []):
            terminalreporter.write_line(f'  {report.nodeid}')


def pytest_pycollect_makeitem(collector, name, obj):
    import re

    if isinstance(obj, type) and re.match(r'.*TestCase$', name):
        return pytest.Class.from_parent(collector, name=name)
    return None


def _deselecionar_mock(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Stubs do ``gerar_banco_mock`` só rodam quando pedidos (``-m mock``).

    Não dá para usar ``-m "not mock"`` no addopts: qualquer ``-m`` da linha de comando o
    sobrescreve (o ``-m "not e2e"`` do job unitário do ``suap_check``, o ``-m e2e`` do job
    e2e). E o stub não pode rodar no job e2e: pedir ``seed_periodo_fechado`` antes da hora
    mudaria o estado para os testes do ``edu``.
    """
    if 'mock' in (config.option.markexpr or ''):
        return
    fora = [item for item in items if item.get_closest_marker('mock')]
    if fora:
        config.hook.pytest_deselected(items=fora)
        items[:] = [item for item in items if not item.get_closest_marker('mock')]


# `tryfirst` por causa do `xdist_group` abaixo: quem traduz o marcador em grupo é o
# `pytest_collection_modifyitems` do próprio xdist (`xdist/remote.py`), que anexa `@<grupo>`
# ao nodeid — e o WorkerInteractor é registrado DEPOIS dos conftests, então na ordem LIFO do
# pytest ele rodaria antes daqui e não veria marcador nenhum. Medido quando o CI rodava
# `-n 4`: sem isto os 49 testes de doc de então se espalham pelos workers e as cadeias do
# `edu` e do `eventos` quebram.
@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config, items):
    _deselecionar_mock(config, items)
    for item in items:
        # Um `xdist_group` por módulo nos testes de doc: o grupo inteiro cai no MESMO
        # worker, e o worker tem banco próprio (`test_suap_doc_e2e_gw<N>`, sufixo do
        # pytest-django). Sem o grupo, o `--dist load` padrão espalharia teste a teste — e as
        # fatias de `edu/tests/doc/` são uma cadeia (turma depende de curso, matrícula de
        # turma) que os seeds de sessão montam por worker.
        #
        # O CI hoje roda `pytest -m doc -n 1 --dist loadgroup` (a escolha por `-n 1` é
        # medida, ver o job `gerar-doc` em `.gitlab-ci.yml`). Sob um worker só o grupo não
        # escolhe worker, mas continua mantendo o módulo CONTÍGUO — que é o que as cadeias
        # acima exigem — e é o que deixa subir o `-n` a um caractere de distância. O teto
        # útil são os 8 módulos com `tests/doc/`.
        if item.get_closest_marker('doc'):
            item.add_marker(pytest.mark.xdist_group(item.nodeid.split('/', 1)[0]))


# O `gerar-doc` roda com `--reruns 2`, e uma tentativa que falha e depois passa não deixa
# rastro: o `-q` não imprime traceback de rerun, e nem `-rR` imprime — ele dá só o NOME do
# teste, que a tabela de durações já dava. O resultado é um flake que se sabe existir e não
# se sabe por quê, como aconteceu com `test_baixar_a_macro_do_siape`, que só se manifesta no
# CI (8 execuções locais seguidas passaram).
#
# Custa nada fora do `gerar-doc`: sem `--reruns` nenhum relatório tem `outcome == 'rerun'`.
def pytest_runtest_logreport(report):
    """Despeja o traceback da tentativa que falhou antes de um rerun."""
    if report.outcome == 'rerun':
        # `sys.stderr.write` e não `print`: o hook `prints` do pre-commit barra `print` no
        # repositório, e diagnóstico de teste é stderr de qualquer forma.
        sys.stderr.write(f'\n[RERUN] {report.nodeid}\n{report.longreprtext}\n')
        sys.stderr.flush()
