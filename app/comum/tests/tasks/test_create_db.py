"""Testes do comando `create_db` (setup do banco sem migrations)."""

import re
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

from django.apps import apps
from django.conf import settings
from django.db import migrations
from django.db.migrations.autodetector import MigrationAutodetector
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.questioner import NonInteractiveMigrationQuestioner
from django.db.migrations.state import ProjectState

from comum.management.commands.create_db import OBJETOS_SQL_DAS_MIGRATIONS, Command, DisableMigrations

CRIACAO_DE_OBJETO = re.compile(
    r'CREATE\s+(?:OR\s+REPLACE\s+)?(?:UNIQUE\s+)?(INDEX|TRIGGER|FUNCTION|VIEW|MATERIALIZED\s+VIEW)\s+(?:CONCURRENTLY\s+)?(?:IF\s+NOT\s+EXISTS\s+)?([\w".]+)',
    re.IGNORECASE,
)


def test_autodetector_com_migrations_desabilitadas() -> None:
    """Reproduz o passo 2 do comando (`migrate --run-syncdb` sem migrations) sem tocar no banco.

    Com `MIGRATION_MODULES` desabilitado o autodetector monta a criação de TODOS os models, e ao
    ordená-los resolve cada `Meta.swappable` com `getattr(settings, <nome>)` — sem default. Qualquer
    setting swappable ausente (ex.: `OAUTH2_PROVIDER_ACCESS_TOKEN_MODEL`) derruba o `create_db`.
    """
    with patch.object(settings, 'MIGRATION_MODULES', DisableMigrations()):
        loader = MigrationLoader(None, ignore_no_migrations=True)
        autodetector = MigrationAutodetector(
            loader.project_state(),
            ProjectState.from_apps(apps),
            NonInteractiveMigrationQuestioner(specified_apps=set(), dry_run=True),
        )
        autodetector.changes(graph=loader.graph)


def _sqls_das_migrations() -> Iterator[str]:
    """Todo SQL cru declarado nas migrations do projeto, incluindo o aninhado em `SeparateDatabaseAndState`.

    O `MIGRATION_MODULES` é forçado para o padrão de cada app: rodando a suíte inteira, o pytest-django
    (`--no-migrations`) o substitui por um `DisableMigrations` de sessão na primeira fixture de banco, e
    o loader devolveria zero migrations — o gate passaria sem olhar nada.
    """

    def operacoes(lista) -> Iterator:
        for operacao in lista:
            if isinstance(operacao, migrations.SeparateDatabaseAndState):
                yield from operacoes(operacao.database_operations)
            else:
                yield operacao

    with patch.object(settings, 'MIGRATION_MODULES', {}):
        disk_migrations = MigrationLoader(None).disk_migrations
    for migration in disk_migrations.values():
        for operacao in operacoes(migration.operations):
            if not isinstance(operacao, migrations.RunSQL):
                continue
            sql = operacao.sql
            for trecho in sql if isinstance(sql, list | tuple) else [sql]:
                yield trecho if isinstance(trecho, str) else trecho[0]


def test_objetos_criados_por_runsql_estao_declarados() -> None:
    """O syncdb não enxerga objeto criado em `RunSQL`; cada um precisa estar tratado no `create_db`.

    Sem este gate, a próxima migration que criar índice/trigger/função por SQL cru some silenciosamente
    das instâncias montadas pelo `create_db` — foi assim que o trigger `check_identificador` sumiu.
    """
    encontrados = {
        f'{re.sub(r"\s+", " ", tipo).lower()} {nome.strip(chr(34)).lower()}'
        for sql in _sqls_das_migrations()
        for tipo, nome in CRIACAO_DE_OBJETO.findall(sql)
    }
    declarados = set(OBJETOS_SQL_DAS_MIGRATIONS)
    assert not encontrados - declarados, f'objetos criados por RunSQL sem tratamento no create_db: {sorted(encontrados - declarados)}'
    # Igualdade nos dois sentidos: se o parser parar de achar o que já existe, o gate vira decoração.
    assert not declarados - encontrados, f'declarados no create_db mas não encontrados nas migrations: {sorted(declarados - encontrados)}'


def _mock_psycopg(banco_existe: bool) -> tuple[MagicMock, MagicMock]:
    cursor = MagicMock()
    cursor.fetchone.return_value = (1,) if banco_existe else None
    conexao = MagicMock()
    conexao.__enter__.return_value = conexao
    conexao.cursor.return_value.__enter__.return_value = cursor
    return conexao, cursor


def _sqls(cursor: MagicMock) -> str:
    return ' '.join(str(chamada.args[0]) for chamada in cursor.execute.call_args_list)


def test_create_database_nao_recria_banco_existente() -> None:
    conexao, cursor = _mock_psycopg(banco_existe=True)
    with patch('comum.management.commands.create_db.psycopg.connect', return_value=conexao):
        Command()._create_database()
    assert 'CREATE DATABASE' not in _sqls(cursor)


def test_create_database_cria_banco_inexistente() -> None:
    conexao, cursor = _mock_psycopg(banco_existe=False)
    with patch('comum.management.commands.create_db.psycopg.connect', return_value=conexao):
        Command()._create_database()
    sqls = _sqls(cursor)
    assert 'CREATE DATABASE' in sqls
    assert f"Identifier('{settings.DATABASES['default']['NAME']}')" in sqls
