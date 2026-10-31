from django.core.management.base import BaseCommand

from boletim_servico import models


class Command(BaseCommand):
    def handle(self, *args, **options):
        # Boletins diários
        for boletim_programado in models.BoletimProgramado.objects.filter(programado=True):
            boletim_programado.gerar_boletim_diario()
        # Boletins semanais
        for boletim_programado in models.BoletimProgramado.objects.filter(programado_semanal=True):
            boletim_programado.gerar_boletim_semanal()
        # Boletins mensais
        for boletim_programado in models.BoletimProgramado.objects.filter(programado_mensal=True):
            boletim_programado.gerar_boletim_mensal()
