from django.conf import settings
from django.db import connections
from django.test.runner import DiscoverRunner


def _execute_create_test_db(self, cursor, parameters, keepdb=False):
    """
    Este é o coração do patch: ele cria o banco e injeta a collation
    antes de retornar o controle para o processo de migration.
    """
    cursor.execute('CREATE DATABASE {dbname} {suffix}'.format(**parameters))
    test_db_name = parameters['dbname'].strip('"').strip("'")  # Remove aspas, se houver

    alias = self.connection.alias
    old_db_name = settings.DATABASES[alias]['NAME']
    old_conn_name = self.connection.settings_dict['NAME']
    self.connection.close()
    settings.DATABASES[alias]['NAME'] = test_db_name
    self.connection.settings_dict['NAME'] = test_db_name
    try:
        with self.connection.cursor() as test_cursor:
            test_cursor.execute('CREATE EXTENSION IF NOT EXISTS unaccent;')
            test_cursor.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm;')
            test_cursor.execute('CREATE EXTENSION IF NOT EXISTS pg_stat_statements;')
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
        settings.DATABASES[alias]['NAME'] = old_db_name
        self.connection.settings_dict['NAME'] = old_conn_name


class DiscoverRunnerPlus(DiscoverRunner):
    def setup_databases(self, **kwargs):
        for alias in connections:
            connection = connections[alias]
            # Substituímos o método interno da classe de criação daquela conexão
            connection.creation._execute_create_test_db = _execute_create_test_db.__get__(connection.creation, connection.creation.__class__)
        return super().setup_databases(**kwargs)
