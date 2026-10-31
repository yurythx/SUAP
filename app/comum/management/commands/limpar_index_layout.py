from comum.models import IndexLayout
from djtools.layout import quadros_cadastrados
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        IndexLayout.objects.exclude(quadro_nome__in=quadros_cadastrados).delete()
