import os

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'suap.settings')
django.setup()

from django.db import connection
from edu.models import Aluno

with connection.cursor() as cursor:
    cursor.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'edu_aluno'
        """
    )
    existentes = {linha[0] for linha in cursor.fetchall()}

with connection.schema_editor() as editor:
    for campo in Aluno._meta.local_fields:
        if campo.column not in existentes:
            editor.add_field(Aluno, campo)
            print('coluna', campo.column)
