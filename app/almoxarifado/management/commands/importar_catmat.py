import os

import pandas as pd
from django.conf import settings
from django.db import transaction

from almoxarifado.models import Catmat
from djtools.management.commands import BaseCommandPlus

BATCH = 1000


class Command(BaseCommandPlus):
    @transaction.atomic
    def handle(self, *args, **options):
        arquivo = os.path.join(settings.BASE_DIR, 'almoxarifado/fixtures/Lista-CATMAT-CATSER-publica-portal-Mai-2019.xlsx')
        self.stdout.write(f'Processando arquivo: {arquivo}')
        df = pd.read_excel(arquivo, header=None)

        existentes = set(Catmat.objects.values_list('codigo', flat=True))
        buffer = []
        seen = set()
        criados = 0
        for _index, row in df.iloc[7:].iterrows():
            codigo = f'{row.iloc[6]:0.0f}'
            if codigo in existentes or codigo in seen:
                continue
            seen.add(codigo)
            buffer.append(Catmat(codigo=codigo, descricao=row.iloc[7]))
            if len(buffer) >= BATCH:
                Catmat.objects.bulk_create(buffer, ignore_conflicts=True)
                criados += len(buffer)
                buffer.clear()
        if buffer:
            Catmat.objects.bulk_create(buffer, ignore_conflicts=True)
            criados += len(buffer)
        self.stdout.write(f'Catmat criados: {criados}')
