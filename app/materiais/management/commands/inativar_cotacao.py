import datetime

from djtools.management.commands import BaseCommandPlus
from materiais.models import MaterialCotacao


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        for cotacao in MaterialCotacao.objects.filter(data_validade__lt=datetime.date.today()):
            cotacao.ativo = False
            cotacao.material.atualizar_valor_medio()
            cotacao.save()
        print('Cotacoes Inativadas.')
