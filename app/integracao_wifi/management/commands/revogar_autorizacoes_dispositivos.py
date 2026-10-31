import datetime

from djtools.management.commands import BaseCommandPlus
from integracao_wifi.models import AutorizacaoDispositivo


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        qs = AutorizacaoDispositivo.objects.exclude(excluida=True)
        qs = qs.filter(data_validade_autorizacao__lt=datetime.datetime.today(), expirada=False)
        for obj in qs:
            obj.revogar_autorizacao()
        print(f'{qs.count()} autorização(ões) de dispositivo(s) revogada(s)')
