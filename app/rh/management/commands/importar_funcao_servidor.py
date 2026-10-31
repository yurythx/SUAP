from djtools.management.commands import BaseCommandPlus
from rh.models import Servidor


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        verbosity = options.get('verbosity', 3)
        Servidor.importar_funcao_servidor(verbosity)
