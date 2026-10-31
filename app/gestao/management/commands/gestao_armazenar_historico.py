from djtools.management.commands import BaseCommandPlus
from gestao.models import HistoricoVariavel, Variavel


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        for variavel in Variavel.objects.all():
            HistoricoVariavel.armazenar_dados(variavel)
