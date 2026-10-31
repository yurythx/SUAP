import os

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'suap.settings')
django.setup()

from django.db import connection

from rh.models import Servidor, Setor

print('setores', Setor.objects.count())
print('servidores', Servidor.objects.count())
with connection.cursor() as cursor:
    cursor.execute(
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name IN ('pessoa_fisica', 'pessoa', 'servidor')
          AND is_nullable = 'NO'
          AND column_default IS NULL
        ORDER BY table_name, ordinal_position
        """
    )
    for row in cursor.fetchall():
        print(row[0], row[1])
