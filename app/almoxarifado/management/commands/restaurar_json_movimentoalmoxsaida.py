import json
import sys
from collections import OrderedDict

from django.db.transaction import atomic

from almoxarifado.models import MovimentoAlmoxSaida
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def add_arguments(self, parser):
        parser.add_argument('models', nargs='*', type=str)

    @atomic
    def handle(self, models, **options):
        data = OrderedDict()
        for arg in models:
            data[arg] = []
        sys.stdin.read()
        arquivo = open('backup.json')
        movimentos = json.load(arquivo)
        arquivo.close()
        for item in movimentos:
            movimento_saida = MovimentoAlmoxSaida.objects.get(id=item['pk'])
            movimento_saida.valor = item['fields']['valor']
            movimento_saida.save()
