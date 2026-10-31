from django.db import connection

from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        cur = connection.cursor()
        sql = 'TRUNCATE TABLE comum_autenticacaodoisfatores;'
        cur.execute(sql)
