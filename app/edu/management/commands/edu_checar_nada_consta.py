import datetime

from djtools.management.commands import BaseCommandPlus
from edu.models import NadaConsta


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        # invalida nada consta expirado
        NadaConsta.objects.filter(valido=True, data_validade__lt=datetime.date.today()).update(valido=False)

        # calcula prazo de validade de nada consta solicitado sem prazo
        qs = NadaConsta.objects.filter(valido=True, prazo_avaliacao__isnull=True, data_solicitacao__isnull=False)
        for nadaconsta in qs:
            nadaconsta.atualizar_prazo_avaliacao()
