import os

from django.core.management import call_command
from django.db import connection

from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        os.system('./bin/clean_pyc.sh')
        call_command('collectstatic')
        print('Limpando a tabela de migrações')
        cur = connection.cursor()
        sql = 'TRUNCATE TABLE django_migrations;'
        cur.execute(sql)
        print('Executando fake em todas as migrações')
        os.system('python manage.py migrate --fake')
