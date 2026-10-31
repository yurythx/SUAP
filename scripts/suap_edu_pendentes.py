import os

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'suap.settings')
django.setup()

from django.db import connection
from django.db.migrations.loader import MigrationLoader

loader = MigrationLoader(connection)
aplicadas = loader.applied_migrations
pendentes = [
    nome
    for (app, nome) in loader.disk_migrations
    if app == 'edu' and (app, nome) not in aplicadas
]
print('edu_pendentes', len(pendentes))
for nome in sorted(pendentes)[:30]:
    print(nome)
