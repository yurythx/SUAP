import os

from django.apps import apps
from django.db import connection

from djtools.management.commands import BaseCommandPlus

Log = apps.get_model('comum', 'log')


def apagar_tabelas_calculos_pagamentos_sql():
    if 'calculos_pagamentos' not in os.listdir():
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE OR REPLACE FUNCTION footgun(IN _schema TEXT, IN _parttionbase TEXT)
                    RETURNS void
                    LANGUAGE plpgsql
                    AS
                    $$
                    DECLARE
                        row     record;
                    BEGIN
                        FOR row IN
                            SELECT
                                table_schema,
                                table_name
                            FROM
                                information_schema.tables
                            WHERE
                                table_type = 'BASE TABLE'
                            AND
                                table_schema = _schema
                            AND
                                table_name ILIKE (_parttionbase || '%')
                        LOOP
                            EXECUTE 'DROP TABLE ' || quote_ident(row.table_schema) || '.' || quote_ident(row.table_name) || ' CASCADE ';
                            RAISE INFO 'Dropped table: %', quote_ident(row.table_schema) || '.' || quote_ident(row.table_name);
                        END LOOP;
                    END;
                    $$;
            """)
            cursor.execute("SELECT footgun('public', 'calculos_pagamentos');")
            cursor.execute('DROP FUNCTION footgun;')
            print(cursor.fetchall())


class Command(BaseCommandPlus):
    help = 'Apagar todas as tabelas do modulo calculos e pagamentos'

    def handle(self, *args, **options):
        apagar_tabelas_calculos_pagamentos_sql()
