import csv
import os

from django.conf import settings
from django.db import transaction

from comum.models import TipoArquivo
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    @transaction.atomic
    def handle(self, *args, **options):
        arquivo_csv = os.path.join(settings.BASE_DIR, 'comum/fixtures/tipo_arquivo_submissao.csv')
        existentes = set(TipoArquivo.objects.values_list('nome', flat=True))
        novos = []
        seen = set()
        with open(arquivo_csv) as csvfile:
            for row in csv.reader(csvfile, delimiter=';'):
                nome = row[0]
                if nome in existentes or nome in seen:
                    continue
                seen.add(nome)
                novos.append(TipoArquivo(nome=nome, extensoes=row[1], eh_video=row[2].lower() == 'true'))
        TipoArquivo.objects.bulk_create(novos, batch_size=1000)
        self.stdout.write(f'TipoArquivo criados: {len(novos)}')
