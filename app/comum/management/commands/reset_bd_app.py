from __future__ import annotations

from collections.abc import Iterable

from django.apps import apps
from django.conf import settings
from django.core.management.base import CommandError, CommandParser
from django.db import connection
from psycopg import sql

from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    help = 'Remove as tabelas e o histórico de migrations aplicadas de um app em ambiente de desenvolvimento.'

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument('app_label', type=str, help='Label do app que será resetado.')

    def handle(self, *args: object, **options: object) -> None:
        if not settings.DEBUG:
            raise CommandError('Este comando só pode ser executado com DEBUG=True.')

        app_label = str(options['app_label'])
        self._validar_app(app_label)

        tabelas = self._buscar_tabelas_do_app(app_label)
        tabelas_removidas = self._remover_tabelas(tabelas)
        migrations_removidas = self._remover_migrations_aplicadas(app_label)

        self.stdout.write(self.style.SUCCESS(f'{len(tabelas_removidas)} tabela(s) removida(s) do app "{app_label}".'))
        self.stdout.write(self.style.SUCCESS(f'{migrations_removidas} migration(s) removida(s) do histórico do app "{app_label}".'))

    def _validar_app(self, app_label: str) -> None:
        try:
            apps.get_app_config(app_label)
        except LookupError as exc:
            raise CommandError(f'App "{app_label}" não encontrado em INSTALLED_APPS.') from exc

    def _buscar_tabelas_do_app(self, app_label: str) -> list[str]:
        tabelas_dos_models = self._buscar_tabelas_dos_models(app_label)
        tabelas_com_prefixo = self._buscar_tabelas_com_prefixo(app_label)
        return sorted(tabelas_dos_models | tabelas_com_prefixo)

    def _buscar_tabelas_dos_models(self, app_label: str) -> set[str]:
        app_config = apps.get_app_config(app_label)
        return {model._meta.db_table for model in app_config.get_models(include_auto_created=True)}

    def _buscar_tabelas_com_prefixo(self, app_label: str) -> set[str]:
        prefixo = f'{app_label}_'
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT c.relname
                  FROM pg_catalog.pg_class c
                  JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                 WHERE n.nspname NOT IN ('pg_catalog', 'pg_toast', 'information_schema')
                   AND c.relkind IN ('r', 'p')
                   AND pg_catalog.pg_table_is_visible(c.oid)
                   AND starts_with(c.relname, %s)
                """,
                [prefixo],
            )
            return {row[0] for row in cursor.fetchall()}

    def _remover_migrations_aplicadas(self, app_label: str) -> int:
        with connection.cursor() as cursor:
            cursor.execute('DELETE FROM django_migrations WHERE app = %s', [app_label])
            return cursor.rowcount

    def _remover_tabelas(self, tabelas: Iterable[str]) -> list[str]:
        tabelas_removidas = []
        with connection.cursor() as cursor:
            for tabela in tabelas:
                cursor.execute(sql.SQL('DROP TABLE IF EXISTS {} CASCADE').format(sql.Identifier(tabela)))
                tabelas_removidas.append(tabela)
                self.stdout.write(f'Tabela "{tabela}" removida.')
        return tabelas_removidas
