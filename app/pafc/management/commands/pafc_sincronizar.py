from djtools.management.commands import BaseCommandPlus
from pafc.models import PAFC


class Command(BaseCommandPlus):
    def check(self, *args, **kwargs):
        pass

    def check_migrations(self, *args, **kwargs):
        pass

    def handle(self, *args, **options):
        for pafc in PAFC.objects.filter(portaria_comissao_elaboracao_vigente__isnull=False):
            pafc.atualizar_situacoes()
