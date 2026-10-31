import os
from datetime import datetime

from django.conf import settings

from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        pg_dump = ['pg_dump']
        if settings.DATABASE_USER:
            pg_dump.append(f'--username={settings.DATABASE_USER}')
        if settings.DATABASE_HOST:
            pg_dump.append(f'--host={settings.DATABASE_HOST}')
        if settings.DATABASE_PORT:
            pg_dump.append(f'--port={settings.DATABASE_PORT}')
        pg_dump.append(settings.DATABASE_NAME)
        pg_dump = ' '.join(pg_dump)

        now = datetime.now()
        backup_name = '{}_{}.sql'.format(settings.DATABASE_NAME, now.strftime('%Y%m%d_%H%M%S'))
        backup_name = os.path.join(settings.PROJECT_ROOT, backup_name)

        print(f'{pg_dump} > {backup_name}')
        os.system(f'{pg_dump} > {backup_name}')
