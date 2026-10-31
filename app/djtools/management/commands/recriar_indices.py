import argparse

from django.db import connection
from django.db.migrations.loader import MigrationLoader

from djtools.db.migrations.indices import recriar_indices_e_unicidades
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    help = 'Recria os índices de FK e as UNIQUE que faltam no banco em relação ao state das migrations (#17730).'

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--dry-run', action='store_true', help='só lista o SQL do que falta, sem executar')

    def handle(self, *args, **options) -> None:
        # Mesmo state do RunPython da comum 0122, mas com as folhas de todo o grafo.
        apps = MigrationLoader(connection).project_state().apps
        with connection.schema_editor(collect_sql=options['dry_run'], atomic=False) as schema_editor:
            recriar_indices_e_unicidades(apps, schema_editor)
        if options['dry_run']:
            faltando = [sql for sql in schema_editor.collected_sql if sql.startswith('CREATE')]
            self.stdout.write('\n'.join(schema_editor.collected_sql))
            self.stdout.write(f'\n{len(faltando)} índice(s) faltando.')
