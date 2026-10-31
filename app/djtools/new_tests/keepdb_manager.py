"""Gerenciamento de ciclo de vida de banco de dados para ``test_behave``.

Este módulo centraliza a lógica de **reutilização e restauração** do banco de
dados de teste quando o runner Behave é executado com os modos avançados de
keepdb.  Ele é consumido exclusivamente por ``djtools.new_tests.runner``.

Modos suportados (mutuamente exclusivos)
-----------------------------------------
``--keepdb-with-data``
    Mantém o banco de teste entre execuções **com todos os dados** gerados
    pelos cenários.  Útil para depuração: permite inspecionar o estado do
    banco após a execução.

``--keepdb-initial-only``
    Mantém o banco entre execuções, mas **restaura-o ao estado da carga
    inicial** a cada nova execução, clonando de um *template* PostgreSQL.
    Acelera o setup em ~90 % comparado a recriar o banco do zero.

``--force-drop-test-db``
    Remove o banco de teste e o template (se existirem) antes de começar.
    Combina-se com qualquer modo keepdb para forçar um bootstrap limpo.

Arquitetura
-----------
O módulo é dividido em duas camadas:

**Funções utilitárias** (nível de módulo):
    Operações atômicas de baixo nível sobre o PostgreSQL — verificar
    existência de banco, clonar via ``CREATE DATABASE ... TEMPLATE``,
    ler/escrever metadados na tabela ``djtools_test_template_meta`` e
    calcular hash de migrations.

**Classe ``KeepDBManager``**:
    Orquestrador de alto nível instanciado pelo ``BehaveTestRunner``.
    Implementa o fluxo de decisão completo: verificar estado do banco,
    restaurar de template, dropar quando necessário, validar compatibilidade
    de migrations e sinalizar ao testcase quando o template precisa ser
    atualizado.

**Mixin ``InitialDataMetaMixin``**:
    Métodos auxiliares de carga inicial e manipulação de metadados,
    injetados em ``MyBehaveTestCase`` via herança múltipla.  Encapsula
    execução de ``TEST_INITIAL_DATA``, criação da tabela de metadados,
    marcação de carga concluída e gravação da origem dos dados.

Tabela de metadados
-------------------
O módulo persiste estado na tabela ``djtools_test_template_meta`` dentro
do próprio banco de teste (e do template).  Chaves utilizadas:

======================  =================================================
Chave                   Descrição
======================  =================================================
``initial_data_loaded`` ``'true'`` quando a carga inicial foi executada
``data_origin``         ``'with_data'`` | ``'initial_only'``
``migration_hash``      SHA-256 da lista de migrations em disco
======================  =================================================

Fluxo de integração com o runner
---------------------------------
::

    BehaveTestRunner.__init__()
        └─ cria KeepDBManager(...)

    BehaveTestRunner.setup_databases()
        ├─ keepdb_manager.prepare_before_setup()   # decisão + clone/drop
        ├─ super().setup_databases()               # Django cria/reusa o DB
        └─ keepdb_manager.persist_migration_hash() # grava hash no DB

    MyBehaveTestCase.setUp()
        ├─ __initial_data()                        # carga fixtures
        └─ refresh_initial_template_if_needed()    # snapshot → template

Exemplo de uso via CLI
----------------------
::

    # Primeira execução (cria banco + template do zero):
    python manage.py test_behave --keepdb-initial-only avaliacao_integrada

    # Execuções seguintes (restaura do template em segundos):
    python manage.py test_behave --keepdb-initial-only avaliacao_integrada

    # Forçar recriação completa:
    python manage.py test_behave --keepdb-initial-only --force-drop-test-db avaliacao_integrada

    # Manter dados dos cenários para inspeção:
    python manage.py test_behave --keepdb-with-data avaliacao_integrada
"""

from __future__ import annotations

import hashlib
import logging
import sys

from django.conf import settings
from django.db import connection, connections
from django.db.migrations.loader import MigrationLoader

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Funções utilitárias de baixo nível
# ---------------------------------------------------------------------------


def add_keepdb_cli_arguments(keepdb_group, parser) -> None:
    """Registra os argumentos de CLI para controle de keepdb no parser do runner.

    Chamado por ``BehaveTestRunner.add_arguments()`` para adicionar as opções
    ``--keepdb-initial-only``, ``--keepdb-with-data`` e ``--force-drop-test-db``
    ao comando ``test_behave``.

    Args:
        keepdb_group: Grupo mutuamente exclusivo do ``argparse`` onde as opções
            ``--keepdb-initial-only`` e ``--keepdb-with-data`` são registradas.
        parser: Parser principal (``ArgumentParser``) onde ``--force-drop-test-db``
            é adicionado (não é mutuamente exclusivo com os demais).
    """
    keepdb_group.add_argument(
        '--keepdb-initial-only',
        dest='keepdb_initial_only',
        action='store_true',
        help='Mantém o banco ao final do teste e preserva apenas os dados iniciais.',
    )
    keepdb_group.add_argument(
        '--keepdb-with-data',
        dest='keepdb_with_data',
        action='store_true',
        help='Mantém o banco ao final do teste com os dados gerados durante a execução.',
    )
    parser.add_argument(
        '--force-drop-test-db',
        dest='force_drop_test_db',
        action='store_true',
        help='Remove o banco de teste no início da execução, caso exista.',
    )


def has_cli_flag(flag: str) -> bool:
    """Verifica se *flag* está presente nos argumentos da linha de comando.

    Args:
        flag: String exata a procurar em ``sys.argv`` (ex.: ``'--keepdb-with-data'``).

    Returns:
        ``True`` se a flag for encontrada.
    """
    return flag in sys.argv


def get_keepdb_mode_from_argv() -> str | None:
    """Determina o modo keepdb ativo a partir de ``sys.argv``.

    Prioridade (mutuamente exclusivos na prática, mas tratados em cascata):

    1. ``--keepdb-with-data``  → retorna ``'with_data'``
    2. ``--keepdb-initial-only`` → retorna ``'initial_only'``
    3. nenhum                   → retorna ``None``

    Returns:
        String identificadora do modo ou ``None``.
    """
    if has_cli_flag('--keepdb-with-data'):
        return 'with_data'
    if has_cli_flag('--keepdb-initial-only'):
        return 'initial_only'
    return None


# ---------------------------------------------------------------------------
# Gerenciamento de conexão
# ---------------------------------------------------------------------------


def _switch_default_connection_db(db_name: str) -> tuple:
    """Redireciona ``connections['default']`` para *db_name* temporariamente.

    Fecha a conexão atual, altera o ``NAME`` tanto no dicionário da conexão
    quanto em ``settings.DATABASES`` e retorna os valores anteriores para
    restauração posterior via :func:`_restore_default_connection_db`.

    Args:
        db_name: Nome do banco PostgreSQL de destino.

    Returns:
        Tupla ``(conn, previous_conn_name, previous_settings_name)``.

    Note:
        Deve **sempre** ser usada em par com :func:`_restore_default_connection_db`
        dentro de um bloco ``try/finally``.
    """
    conn = connections['default']
    previous_conn_name = conn.settings_dict['NAME']
    previous_settings_name = settings.DATABASES['default']['NAME']
    conn.close()
    conn.settings_dict['NAME'] = db_name
    settings.DATABASES['default']['NAME'] = db_name
    return conn, previous_conn_name, previous_settings_name


def _restore_default_connection_db(conn, previous_conn_name: str, previous_settings_name: str) -> None:
    """Restaura ``connections['default']`` ao banco original.

    Args:
        conn: Objeto de conexão retornado por :func:`_switch_default_connection_db`.
        previous_conn_name: Nome anterior em ``conn.settings_dict``.
        previous_settings_name: Nome anterior em ``settings.DATABASES``.
    """
    conn.close()
    conn.settings_dict['NAME'] = previous_conn_name
    settings.DATABASES['default']['NAME'] = previous_settings_name


# ---------------------------------------------------------------------------
# Operações sobre bancos PostgreSQL
# ---------------------------------------------------------------------------


def db_exists(db_name: str, admin_db_name: str) -> bool:
    """Verifica se o banco *db_name* existe no servidor PostgreSQL.

    Conecta-se ao *admin_db_name* (tipicamente o banco de desenvolvimento)
    para consultar ``pg_database``.

    Args:
        db_name: Nome do banco a verificar.
        admin_db_name: Banco usado para executar a consulta administrativa.

    Returns:
        ``True`` se o banco existir.
    """
    conn, prev_conn, prev_settings = _switch_default_connection_db(admin_db_name)
    try:
        conn.ensure_connection()
        with conn.cursor() as cursor:
            cursor.execute('SELECT 1 FROM pg_database WHERE datname=%s', [db_name])
            return cursor.fetchone() is not None
    finally:
        _restore_default_connection_db(conn, prev_conn, prev_settings)


def clone_database(source_db_name: str, target_db_name: str, admin_db_name: str) -> None:
    """Clona *source_db_name* para *target_db_name* via ``CREATE DATABASE ... TEMPLATE``.

    Operação destrutiva: se *target_db_name* já existir ele é removido antes
    da clonagem.  Conexões ativas em ambos os bancos são encerradas.

    Args:
        source_db_name: Banco de origem (template).
        target_db_name: Banco de destino (será recriado).
        admin_db_name: Banco administrativo para executar DDL.

    Raises:
        RuntimeError: Se *source_db_name* não existir.

    Note:
        Nomes de banco são interpolados via f-string no SQL por limitação do
        PostgreSQL (DDL não aceita parâmetros ``%s``).  Os nomes são sempre
        derivados internamente (nunca de entrada do usuário), portanto o risco
        de SQL injection é mitigado.
    """
    conn, prev_conn, prev_settings = _switch_default_connection_db(admin_db_name)
    try:
        conn.ensure_connection()
        conn.connection.autocommit = True
        with conn.cursor() as cursor:
            # Valida existência do banco de origem
            cursor.execute('SELECT 1 FROM pg_database WHERE datname=%s', [source_db_name])
            if not cursor.fetchone():
                raise RuntimeError(f'Banco de origem para template não existe: {source_db_name}')

            # Remove banco de destino se existir
            cursor.execute(
                'SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s AND pid <> pg_backend_pid()',
                [target_db_name],
            )
            cursor.execute('SELECT 1 FROM pg_database WHERE datname=%s', [target_db_name])
            if cursor.fetchone():
                cursor.execute(f'DROP DATABASE "{target_db_name}"')

            # Clona
            cursor.execute(
                'SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s AND pid <> pg_backend_pid()',
                [source_db_name],
            )
            cursor.execute(f'CREATE DATABASE "{target_db_name}" TEMPLATE "{source_db_name}"')
    finally:
        _restore_default_connection_db(conn, prev_conn, prev_settings)


# ---------------------------------------------------------------------------
# Leitura/escrita de metadados
# ---------------------------------------------------------------------------


def read_meta_value(db_name: str, key: str) -> str | None:
    """Lê um valor da tabela ``djtools_test_template_meta`` no banco *db_name*.

    Retorna ``None`` se a tabela não existir ou a chave não for encontrada.

    Args:
        db_name: Banco onde a tabela de metadados está.
        key: Chave a consultar.

    Returns:
        Valor associado à chave ou ``None``.
    """
    conn, prev_conn, prev_settings = _switch_default_connection_db(db_name)
    try:
        conn.ensure_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT to_regclass('public.djtools_test_template_meta')")
            if cursor.fetchone()[0] is None:
                return None
            cursor.execute('SELECT value FROM djtools_test_template_meta WHERE key=%s', [key])
            row = cursor.fetchone()
            return row[0] if row else None
    finally:
        _restore_default_connection_db(conn, prev_conn, prev_settings)


def write_meta_value(db_name: str, key: str, value: str) -> None:
    """Escreve ou atualiza um valor na tabela ``djtools_test_template_meta``.

    Cria a tabela caso ela ainda não exista (``CREATE TABLE IF NOT EXISTS``).

    Args:
        db_name: Banco alvo.
        key: Chave do metadado.
        value: Valor a persistir.
    """
    conn, prev_conn, prev_settings = _switch_default_connection_db(db_name)
    try:
        conn.ensure_connection()
        with conn.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS djtools_test_template_meta (
                    key VARCHAR(100) PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cursor.execute(
                """
                INSERT INTO djtools_test_template_meta (key, value)
                VALUES (%s, %s)
                ON CONFLICT (key)
                DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
                """,
                [key, value],
            )
    finally:
        _restore_default_connection_db(conn, prev_conn, prev_settings)


# ---------------------------------------------------------------------------
# Hash de migrations
# ---------------------------------------------------------------------------


def calculate_migration_hash() -> str:
    """Calcula hash SHA-256 determinístico de todas as migrations em disco.

    O hash é derivado da lista ordenada ``app_label.migration_name`` de todas
    as migrations conhecidas pelo ``MigrationLoader``.  Ele permite detectar
    quando um banco reutilizado via keepdb está desatualizado em relação ao
    código.

    Returns:
        String hexadecimal de 64 caracteres (SHA-256).
    """
    loader = MigrationLoader(connections['default'], ignore_no_migrations=True)
    keys = sorted(loader.disk_migrations.keys())
    payload = '|'.join(f'{app}.{name}' for app, name in keys)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


# ---------------------------------------------------------------------------
# Refresh do template inicial
# ---------------------------------------------------------------------------


def refresh_initial_template_if_needed() -> None:
    """Cria/atualiza o banco *template inicial* a partir do banco de teste atual.

    Chamado em ``MyBehaveTestCase.setUp()`` **após** a carga inicial.  Somente
    executa quando ``settings.BEHAVE_TEMPLATE_NEEDS_REFRESH`` é ``True``
    (sinalizado por :meth:`KeepDBManager.prepare_before_setup` quando o
    template não existe ou está desatualizado).

    O template é um snapshot (clone PostgreSQL) do banco de teste no momento
    em que ele contém apenas os dados iniciais (fixtures + ``initial_data``).
    Nas execuções seguintes, o banco de teste é restaurado desse template em
    vez de refazer todo o bootstrap.

    Settings utilizados:
        - ``BEHAVE_TEMPLATE_NEEDS_REFRESH`` (bool): flag de controle.
        - ``BEHAVE_INITIAL_TEMPLATE_DB`` (str): nome do banco template.
        - ``BEHAVE_DB_ADMIN_NAME`` (str): banco administrativo para DDL.
    """
    keep_mode = get_keepdb_mode_from_argv()
    if keep_mode not in ('initial_only', 'with_data'):
        return
    if not getattr(settings, 'BEHAVE_TEMPLATE_NEEDS_REFRESH', False):
        return

    template_db_name = getattr(settings, 'BEHAVE_INITIAL_TEMPLATE_DB', None)
    admin_db_name = getattr(settings, 'BEHAVE_DB_ADMIN_NAME', None) or settings.DATABASES['default']['NAME']
    if not template_db_name:
        return

    test_db_name = connections['default'].creation._get_test_db_name()
    logger.info(
        '[test_behave] Criando/atualizando template inicial a partir do banco de teste: %s -> %s',
        test_db_name,
        template_db_name,
    )
    clone_database(test_db_name, template_db_name, admin_db_name)
    write_meta_value(template_db_name, 'migration_hash', calculate_migration_hash())
    settings.BEHAVE_TEMPLATE_NEEDS_REFRESH = False
    logger.info('[test_behave] Template inicial atualizado com sucesso.')


# ---------------------------------------------------------------------------
# Classe orquestradora
# ---------------------------------------------------------------------------


class KeepDBManager:
    """Orquestrador do ciclo de vida do banco de teste para modos keepdb.

    Instanciado pelo ``BehaveTestRunner`` durante ``__init__`` e utilizado em
    ``setup_databases`` para preparar o banco antes que o Django execute seu
    próprio setup.

    Atributos:
        admin_db_name: Banco PostgreSQL usado para operações administrativas
            (``CREATE/DROP DATABASE``).  Normalmente é o banco de desenvolvimento.
        keepdb: ``True`` quando ``--keepdb`` (ou derivados) está ativo.
            Atualizado pelo runner em ``setup_databases`` com o valor final.
        keepdb_with_data: ``True`` para modo ``--keepdb-with-data``.
        keepdb_initial_only: ``True`` para modo ``--keepdb-initial-only``.
        force_drop_test_db: ``True`` para ``--force-drop-test-db``.

    Ciclo de vida típico::

        manager = KeepDBManager(...)
        manager.prepare_before_setup()  # antes de super().setup_databases()
        # ... Django cria/reusa o banco ...
        manager.persist_migration_hash_if_needed()  # após setup_databases()
    """

    def __init__(
        self,
        *,
        admin_db_name: str,
        keepdb: bool,
        keepdb_with_data: bool,
        keepdb_initial_only: bool,
        force_drop_test_db: bool,
    ):
        self.admin_db_name = admin_db_name
        self.keepdb = keepdb
        self.keepdb_with_data = keepdb_with_data
        self.keepdb_initial_only = keepdb_initial_only
        self.force_drop_test_db = force_drop_test_db
        self.logger = logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # Configuração de runtime
    # ------------------------------------------------------------------

    def configure_runtime_settings(self) -> tuple[str, str]:
        """Inicializa settings dinâmicos para integração runner ↔ testcase.

        Define em ``settings``:
            - ``BEHAVE_INITIAL_TEMPLATE_DB``: nome do banco template (``<test_db>_template_initial``).
            - ``BEHAVE_DB_ADMIN_NAME``: banco administrativo.
            - ``BEHAVE_TEMPLATE_NEEDS_REFRESH``: flag inicializada como ``False``.

        Returns:
            Tupla ``(test_db_name, template_db_name)``.
        """
        test_db_name = connections['default'].creation._get_test_db_name()
        template_db_name = f'{test_db_name}_template_initial'
        settings.BEHAVE_INITIAL_TEMPLATE_DB = template_db_name
        settings.BEHAVE_DB_ADMIN_NAME = self.admin_db_name
        settings.BEHAVE_TEMPLATE_NEEDS_REFRESH = False
        return test_db_name, template_db_name

    # ------------------------------------------------------------------
    # Fluxo principal
    # ------------------------------------------------------------------

    def prepare_before_setup(self) -> None:
        """Prepara o banco de teste antes de ``super().setup_databases()``.

        Fluxo de decisão:

        1. **Modo keepdb ativo** (``initial_only`` ou ``with_data``),
           sem ``--force-drop-test-db``:

           a. ``initial_only``: sempre restaura do template quando ele é válido.
           b. ``with_data``: só restaura quando o banco ainda não está marcado.
           c. Se template não existe ou está desatualizado → **dropa** banco e
              template, sinaliza ``BEHAVE_TEMPLATE_NEEDS_REFRESH = True`` para
              que o testcase crie um novo template após a carga inicial.

        2. **Validação de hash** (keepdb ativo): garante que o banco
           reutilizado foi criado com as mesmas migrations do código atual.
           Aborta com ``RuntimeError`` se divergir.

        3. **``--force-drop-test-db``**: remove banco e template
           incondicionalmente.  Se combinado com keepdb, sinaliza refresh.
        """
        test_db_name, template_db_name = self.configure_runtime_settings()
        self.logger.info(
            '[test_behave] Preparando banco de teste. test_db=%s template=%s keepdb=%s with_data=%s initial_only=%s force_drop=%s',
            test_db_name,
            template_db_name,
            self.keepdb,
            self.keepdb_with_data,
            self.keepdb_initial_only,
            self.force_drop_test_db,
        )
        self.logger.info('[test_behave] Verificando estado atual do banco de teste...')
        self.log_test_db_state()

        # --- Lógica de restauração/reuso (somente em modos keepdb) ---
        if (self.keepdb_initial_only or self.keepdb_with_data) and not self.force_drop_test_db:
            if self.keepdb_initial_only:
                # Em initial-only a garantia é sempre iniciar do snapshot inicial.
                if self.is_initial_template_valid(template_db_name):
                    self.logger.info(
                        '[test_behave] keepdb-initial-only: restaurando banco de teste a partir do template: %s -> %s',
                        template_db_name,
                        test_db_name,
                    )
                    clone_database(template_db_name, test_db_name, self.admin_db_name)
                else:
                    template_exists = self.test_db_exists(template_db_name)
                    if not template_exists:
                        self.logger.info(
                            '[test_behave] Template inicial não existe (%s). Ele será criado nesta execução.',
                            template_db_name,
                        )
                    else:
                        self.logger.info(
                            '[test_behave] Template inicial desatualizado (%s). Ele será recriado nesta execução.',
                            template_db_name,
                        )
                    self.logger.info('[test_behave] Banco de teste será recriado e o template inicial será atualizado.')
                    self.drop_test_db_if_exists()
                    settings.BEHAVE_TEMPLATE_NEEDS_REFRESH = True
            else:
                # keepdb-with-data: tenta reaproveitar o banco já marcado.
                needs_bootstrap = not self.is_test_db_marked(test_db_name)
                if not needs_bootstrap:
                    self.logger.info(
                        '[test_behave] Banco de teste já está marcado (%s). Pulando restauração a partir do template.',
                        test_db_name,
                    )
                else:
                    if self.is_initial_template_valid(template_db_name):
                        self.logger.info(
                            '[test_behave] Banco de teste será criado a partir do template inicial: %s -> %s',
                            template_db_name,
                            test_db_name,
                        )
                        clone_database(template_db_name, test_db_name, self.admin_db_name)
                    else:
                        template_exists = self.test_db_exists(template_db_name)
                        if not template_exists:
                            self.logger.info(
                                '[test_behave] Template inicial não existe (%s). Ele será criado nesta execução.',
                                template_db_name,
                            )
                        else:
                            self.logger.info(
                                '[test_behave] Template inicial desatualizado (%s). Ele será recriado nesta execução.',
                                template_db_name,
                            )
                        self.logger.info('[test_behave] Banco de teste será recriado e o template inicial será atualizado.')
                        self.drop_test_db_if_exists()
                        settings.BEHAVE_TEMPLATE_NEEDS_REFRESH = True

        # --- Validação de hash de migrations ---
        if self.keepdb and (self.keepdb_with_data or self.keepdb_initial_only) and not self.force_drop_test_db:
            self.logger.info('[test_behave] Validando compatibilidade de migrations do banco reutilizado...')
            self.validate_keepdb_migration_hash()

        # --- Drop forçado ---
        if self.force_drop_test_db:
            self.logger.info('[test_behave] --force-drop-test-db ativo: removendo banco de teste e template inicial...')
            self.drop_test_db_if_exists()
            if self.keepdb_with_data or self.keepdb_initial_only:
                settings.BEHAVE_TEMPLATE_NEEDS_REFRESH = True

    def persist_migration_hash_if_needed(self) -> None:
        """Grava o hash de migrations no banco de teste (pós ``setup_databases``).

        Executado apenas quando keepdb está ativo com um modo explícito.
        Garante que execuções futuras possam validar compatibilidade.
        """
        if self.keepdb and (self.keepdb_with_data or self.keepdb_initial_only):
            self.persist_migration_hash_on_test_db()

    # ------------------------------------------------------------------
    # Operações de banco
    # ------------------------------------------------------------------

    def drop_db_if_exists(self, db_name: str) -> None:
        """Remove um banco PostgreSQL, encerrando conexões ativas previamente.

        Conecta-se ao banco administrativo (``self.admin_db_name``) para
        executar o ``DROP DATABASE``.  Falhas são logadas como warning sem
        propagar exceção (operação best-effort).

        Args:
            db_name: Nome do banco a remover.
        """
        conn, prev_conn, prev_settings = _switch_default_connection_db(self.admin_db_name)
        try:
            self.logger.info('[test_behave] Conectando ao banco administrativo para verificar/remover: %s', db_name)
            conn.ensure_connection()
            conn.connection.autocommit = True
            with conn.cursor() as cursor:
                cursor.execute('SELECT 1 FROM pg_database WHERE datname=%s', [db_name])
                if not cursor.fetchone():
                    self.logger.info('[test_behave] Banco não existe: %s.', db_name)
                    return
                self.logger.info('[test_behave] Removendo banco existente: %s.', db_name)
                cursor.execute(
                    'SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s AND pid <> pg_backend_pid()',
                    [db_name],
                )
                cursor.execute(f'DROP DATABASE "{db_name}"')
        except Exception as exc:
            self.logger.warning('[test_behave] Falha ao remover banco %s: %s', db_name, exc)
        finally:
            _restore_default_connection_db(conn, prev_conn, prev_settings)

    def drop_test_db_if_exists(self) -> None:
        """Remove o banco de teste **e** seu template inicial.

        Ambos são derivados do nome retornado por
        ``connections['default'].creation._get_test_db_name()``.
        """
        test_db_name = connections['default'].creation._get_test_db_name()
        template_db_name = f'{test_db_name}_template_initial'
        self.logger.info(
            '[test_behave] Iniciando limpeza de bancos de teste: principal=%s template=%s',
            test_db_name,
            template_db_name,
        )
        self.drop_db_if_exists(test_db_name)
        self.drop_db_if_exists(template_db_name)

    # ------------------------------------------------------------------
    # Diagnóstico / logging
    # ------------------------------------------------------------------

    def log_test_db_state(self) -> None:
        """Registra no log o estado atual e o modo de operação do banco de teste.

        Informa se o banco existe, qual modo keepdb está ativo e qual
        a origem dos dados (``initial_only``, ``with_data`` ou desconhecida).
        """
        test_db_name = connections['default'].creation._get_test_db_name()
        try:
            self.logger.info('[test_behave] Consultando existência do banco de teste: %s', test_db_name)
            with connections['default'].cursor() as cursor:
                cursor.execute('SELECT 1 FROM pg_database WHERE datname=%s', [test_db_name])
                exists = cursor.fetchone() is not None
        except Exception as exc:
            self.logger.warning('[test_behave] Não foi possível verificar o banco de teste: %s', exc)
            return

        if not exists:
            if self.keepdb:
                self.logger.info('[test_behave] Banco de teste será criado: %s (keepdb ativo).', test_db_name)
            else:
                self.logger.info('[test_behave] Banco de teste será criado: %s (será apagado ao final).', test_db_name)
            return

        if not self.keepdb:
            self.logger.info('[test_behave] Banco de teste será criado: %s (será apagado ao final).', test_db_name)
            return

        # Banco existe e keepdb está ativo — reportar estado
        keep_mode = 'with_data' if self.keepdb_with_data else 'initial_only' if self.keepdb_initial_only else None
        data_flag = self.read_initial_data_flag(test_db_name)

        # Determina a descrição com base no modo solicitado ou no marcador gravado
        effective = keep_mode or data_flag
        if effective == 'with_data':
            desc = '(dados de execuções anteriores)'
        elif effective == 'initial_only':
            desc = '(somente dados iniciais)'
        else:
            desc = ''

        self.logger.info(
            '[test_behave] Usando banco de teste existente: %s %s',
            test_db_name,
            desc,
        )

    # ------------------------------------------------------------------
    # Leitura de metadados
    # ------------------------------------------------------------------

    def read_initial_data_flag(self, test_db_name: str) -> str | None:
        """Lê o marcador de origem dos dados do banco de teste.

        Consulta as chaves ``data_origin`` e ``initial_data_loaded`` na tabela
        de metadados para determinar se o banco contém dados iniciais, dados
        completos ou estado desconhecido.

        Args:
            test_db_name: Nome do banco a consultar.

        Returns:
            ``'with_data'``, ``'initial_only'`` ou ``None``.
        """
        conn, prev_conn, prev_settings = _switch_default_connection_db(test_db_name)
        try:
            conn.ensure_connection()
            with conn.cursor() as cursor:
                cursor.execute("SELECT value FROM djtools_test_template_meta WHERE key='initial_data_loaded'")
                row = cursor.fetchone()
                cursor.execute("SELECT value FROM djtools_test_template_meta WHERE key='data_origin'")
                origin_row = cursor.fetchone()

            if origin_row and origin_row[0] == 'with_data':
                return 'with_data'
            if origin_row and origin_row[0] == 'initial_only':
                return 'initial_only'
            if row and row[0] == 'true':
                return 'initial_only'
            return None
        except Exception as exc:
            self.logger.warning('[test_behave] Não foi possível ler metadados do banco de teste: %s', exc)
            return None
        finally:
            _restore_default_connection_db(conn, prev_conn, prev_settings)

    def test_db_exists(self, db_name: str) -> bool:
        """Verifica existência de banco via :func:`db_exists`.

        Args:
            db_name: Nome do banco a verificar.
        """
        return db_exists(db_name, self.admin_db_name)

    def read_test_db_meta_value(self, db_name: str, key: str) -> str | None:
        """Lê metadado de banco específico via :func:`read_meta_value`."""
        return read_meta_value(db_name, key)

    def write_test_db_meta_value(self, db_name: str, key: str, value: str) -> None:
        """Escreve metadado em banco específico via :func:`write_meta_value`."""
        write_meta_value(db_name, key, value)

    # ------------------------------------------------------------------
    # Validação de migrations
    # ------------------------------------------------------------------

    def validate_keepdb_migration_hash(self) -> None:
        """Valida que o banco reutilizado é compatível com as migrations atuais.

        Compara o hash de migrations gravado no banco (chave ``migration_hash``)
        com o hash calculado a partir dos arquivos em disco.

        Raises:
            RuntimeError: Se o hash divergir ou estiver ausente.
                A mensagem orienta o usuário a usar ``--force-drop-test-db``.
        """
        test_db_name = connections['default'].creation._get_test_db_name()
        self.logger.info('[test_behave] Conferindo hash de migrations do banco de teste: %s', test_db_name)
        if not self.test_db_exists(test_db_name):
            return
        current_hash = calculate_migration_hash()
        stored_hash = self.read_test_db_meta_value(test_db_name, 'migration_hash')
        if stored_hash and stored_hash == current_hash:
            return
        if stored_hash is None:
            raise RuntimeError('[test_behave] Banco de teste existente sem hash de migrations. Use --force-drop-test-db para recriar.')
        raise RuntimeError('[test_behave] Banco de teste desatualizado: hash de migrations divergente. Use --force-drop-test-db para recriar.')

    def persist_migration_hash_on_test_db(self) -> None:
        """Grava o hash de migrations atual na tabela de metadados do banco de teste."""
        test_db_name = connections['default'].creation._get_test_db_name()
        if not self.test_db_exists(test_db_name):
            return
        self.write_test_db_meta_value(test_db_name, 'migration_hash', calculate_migration_hash())
        self.logger.info('[test_behave] Hash de migrations atualizado no banco de teste.')

    # ------------------------------------------------------------------
    # Verificações de estado
    # ------------------------------------------------------------------

    def is_initial_template_valid(self, template_db_name: str) -> bool:
        """Verifica se o template inicial existe e tem hash de migrations compatível.

        Args:
            template_db_name: Nome do banco template.

        Returns:
            ``True`` se o template pode ser usado para restauração.
        """
        if not self.test_db_exists(template_db_name):
            return False
        stored_hash = self.read_test_db_meta_value(template_db_name, 'migration_hash')
        if not stored_hash:
            return False
        return stored_hash == calculate_migration_hash()

    def is_test_db_already_initial_only(self, test_db_name: str) -> bool:
        """Verifica se o banco de teste já está no estado ``initial_only`` válido.

        Condições:
            1. O banco existe.
            2. Está marcado como ``initial_only`` (chave ``data_origin`` ou
               ``initial_data_loaded``).
            3. O hash de migrations é compatível com o código atual.

        Args:
            test_db_name: Nome do banco de teste.

        Returns:
            ``True`` se todas as condições forem satisfeitas.
        """
        if not self.test_db_exists(test_db_name):
            return False
        if self.read_initial_data_flag(test_db_name) != 'initial_only':
            return False
        stored_hash = self.read_test_db_meta_value(test_db_name, 'migration_hash')
        if not stored_hash:
            return False
        return stored_hash == calculate_migration_hash()

    def is_test_db_marked(self, test_db_name: str) -> bool:
        """Verifica se o banco possui qualquer marcação de origem de dados.

        Usado pelo modo ``--keepdb-with-data`` para determinar se o banco
        pode ser reutilizado como está (independente do tipo de marcação).

        Args:
            test_db_name: Nome do banco de teste.

        Returns:
            ``True`` se o banco existir e tiver marcação ``with_data`` ou
            ``initial_only``.
        """
        if not self.test_db_exists(test_db_name):
            return False
        data_origin = self.read_test_db_meta_value(test_db_name, 'data_origin')
        if data_origin in ('with_data', 'initial_only'):
            return True
        return self.read_initial_data_flag(test_db_name) in ('with_data', 'initial_only')


class InitialDataMetaMixin:
    """Mixin que fornece helpers de carga inicial e metadados para o testcase.

    Injetado em ``MyBehaveTestCase`` via herança múltipla, fornece métodos
    para executar a carga inicial de dados (``TEST_INITIAL_DATA``), gerenciar
    a tabela ``djtools_test_template_meta`` e marcar o estado do banco.

    Diferente das funções de módulo (que trocam de conexão via
    :func:`_switch_default_connection_db`), estes métodos operam sobre a
    conexão ``default`` corrente — ou seja, o banco de teste já ativo no
    contexto do ``TestCase``.

    Métodos:
        _run_initial_data_load: Executa todas as funções de carga inicial.
        _ensure_template_meta_table: Cria a tabela de metadados se necessário.
        _initial_data_already_loaded: Verifica se a carga já foi executada.
        _mark_initial_data_loaded: Marca a carga como concluída.
        _set_data_origin: Grava a origem dos dados (``with_data`` / ``initial_only``).

    Note:
        Espera que a classe que herda possua o atributo ``self.verbosity``
        (definido por ``MyBehaveTestCase.__init__``).
    """

    def _run_initial_data_load(self) -> None:
        """Executa todas as funções de carga inicial registradas em ``settings.TEST_INITIAL_DATA``.

        Cada entrada é um caminho pontilhado no formato
        ``app.features.test_initial_data.initial_data``.  O módulo é importado
        dinamicamente e a função final é chamada com ``self.verbosity - 1``.
        """
        for carga in settings.TEST_INITIAL_DATA:
            modulo = __import__(carga[: carga.rindex('.')], fromlist=carga[: carga.rindex('.')])
            str_funcao = carga[carga.rindex('.') + 1 :]

            if hasattr(modulo, str_funcao):
                funcao = getattr(modulo, str_funcao)
                funcao(self.verbosity - 1)

    def _ensure_template_meta_table(self) -> None:
        """Cria a tabela ``djtools_test_template_meta`` caso não exista.

        Usa ``CREATE TABLE IF NOT EXISTS`` para ser idempotente.  Opera
        sobre a conexão ``default`` corrente (banco de teste ativo).
        """
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS djtools_test_template_meta (
                    key VARCHAR(100) PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )

    def _initial_data_already_loaded(self) -> bool:
        """Verifica se a carga inicial já foi executada neste banco.

        Consulta a chave ``initial_data_loaded`` na tabela de metadados.

        Returns:
            ``True`` se a chave existir com valor ``'true'``.
            ``False`` em caso de erro ou chave ausente.
        """
        try:
            self._ensure_template_meta_table()
            with connection.cursor() as cursor:
                cursor.execute("SELECT value FROM djtools_test_template_meta WHERE key='initial_data_loaded'")
                row = cursor.fetchone()
            return bool(row and row[0] == 'true')
        except Exception:
            return False

    def _mark_initial_data_loaded(self) -> None:
        """Marca a carga inicial como concluída no banco de teste.

        Insere/atualiza a chave ``initial_data_loaded`` com valor ``'true'``.
        Usado pelo testcase para evitar re-executar a carga em execuções
        subsequentes com keepdb.
        """
        self._ensure_template_meta_table()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO djtools_test_template_meta (key, value)
                VALUES ('initial_data_loaded', 'true')
                ON CONFLICT (key)
                DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
                """
            )

    def _set_data_origin(self, value: str) -> None:
        """Grava a origem dos dados do banco de teste.

        Insere/atualiza a chave ``data_origin`` com o valor informado.
        Chamado por ``_fixture_teardown`` para registrar se o banco foi
        preservado com dados completos (``'with_data'``) ou apenas
        iniciais (``'initial_only'``).

        Args:
            value: Identificador da origem — ``'with_data'`` ou ``'initial_only'``.
        """
        self._ensure_template_meta_table()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO djtools_test_template_meta (key, value)
                VALUES ('data_origin', %s)
                ON CONFLICT (key)
                DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
                """,
                [value],
            )
