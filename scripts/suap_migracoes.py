import os

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'suap.settings')
django.setup()

from django.db import connection
from django.db.migrations.executor import MigrationExecutor

executor = MigrationExecutor(connection)
pendentes = executor.migration_plan(executor.loader.graph.leaf_nodes())
print('pendentes', len(pendentes))
for migration, _ in pendentes[:40]:
    print(migration.app_label, migration.name)
