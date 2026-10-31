from django.core.management.base import BaseCommand, CommandError

from djtools.new_tests.db_preflight import database_access_summary, ensure_database_access


class Command(BaseCommand):
    help = 'Valida acesso ao banco configurado em DATABASES[default].'

    def add_arguments(self, parser):
        parser.add_argument(
            '--purpose',
            default='check_db_access',
            help='Contexto textual usado na mensagem de erro.',
        )

    def handle(self, *args, **options):
        purpose = options['purpose']
        self.stdout.write(f'[db_preflight] {database_access_summary()}')
        try:
            result = ensure_database_access(purpose=purpose)
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(f'[db_preflight] {result.message}')
