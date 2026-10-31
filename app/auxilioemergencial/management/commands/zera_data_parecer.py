from auxilioemergencial.models import SEM_PARECER, InscricaoDispositivo, InscricaoInternet, InscricaoMaterialPedagogico
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        InscricaoInternet.objects.filter(parecer=SEM_PARECER).update(data_parecer=None)
        InscricaoDispositivo.objects.filter(parecer=SEM_PARECER).update(data_parecer=None)
        InscricaoMaterialPedagogico.objects.filter(parecer=SEM_PARECER).update(data_parecer=None)
