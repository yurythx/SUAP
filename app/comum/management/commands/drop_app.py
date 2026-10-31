"""
Comando que remove todas as tables, views, sequences e index de uma aplicacao.
"""

from django.db import connection
from django.utils import termcolors

from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        if args:
            cursor = connection.cursor()
            try:
                app = args[0] + '_%%'
                sql = f"""SELECT c.relname as name
                                FROM pg_catalog.pg_class c
                                LEFT JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                                WHERE n.nspname NOT IN ('pg_catalog', 'pg_toast')
                                AND c.relkind = 'r'
                                AND pg_catalog.pg_table_is_visible(c.oid)
                                AND c.relname like '{app}';"""
                cursor.execute(sql)

                for row in cursor.fetchall():
                    cursor.execute(f'drop table {row} cascade')
                    connection._commit()
                    print(termcolors.make_style(fg='cyan', opts=('bold',))(f'{row} removed'))

                print(termcolors.make_style(fg='yellow', opts=('bold',))(f'{args[0]} removed'))
            except Exception as e:
                connection._rollback()
                print(termcolors.make_style(fg='cyan', opts=('bold',))(f'Error: {e}'))
        else:
            print(termcolors.make_style(fg='cyan', opts=('bold',))('Error: app not informed'))
