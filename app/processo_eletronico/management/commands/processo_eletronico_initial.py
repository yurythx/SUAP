from django.core.management import call_command

from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        verbosity = options.get('verbosity', 1)
        call_command('loaddata', '../fixtures/initial_tipo_processo.json', verbosity=verbosity)
