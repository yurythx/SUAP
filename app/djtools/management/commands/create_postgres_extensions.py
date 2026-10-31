import logging

from django.db import connection

from djtools.management.commands import BaseCommandPlus

logger = logging.getLogger(__name__)


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        logger.info('Criando extensões do postgres')
        with connection.cursor() as cursor:
            cursor.execute('CREATE EXTENSION IF NOT EXISTS unaccent;')
            cursor.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm;')
            cursor.execute("""
                CREATE OR REPLACE FUNCTION f_unaccent(text) RETURNS text AS
                $func$
                SELECT unaccent('unaccent', upper($1))
                $func$  LANGUAGE sql IMMUTABLE SET search_path = public, pg_temp;
            """)
            cursor.execute('CREATE EXTENSION IF NOT EXISTS pg_stat_statements;')
            cursor.execute("""
                CREATE COLLATION IF NOT EXISTS ignore_accents_case ( provider = 'icu', locale = 'pt-BR-u-ks-level1', deterministic = false);
            """)
