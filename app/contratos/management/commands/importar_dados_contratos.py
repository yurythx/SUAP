import csv
import os

from django.conf import settings
from django.db import transaction

from contratos.models import PreConfiguracaoAgenda
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    @transaction.atomic
    def handle(self, *args, **options):
        file_path = os.path.join(settings.BASE_DIR, 'contratos/fixtures/pre_configuracao_agenda.csv')
        with open(file_path) as file:
            reader = csv.reader(file)
            next(reader)
            objs = [
                PreConfiguracaoAgenda(gatilho='MOE', acao=acao, prazo=prazo, recorrente=(recorrente == 'Sim'))
                for prazo, _gatilho, acao, recorrente in reader
            ]
        PreConfiguracaoAgenda.objects.bulk_create(objs)
