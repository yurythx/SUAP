from datetime import datetime, timedelta

from django.core.management.base import BaseCommand

from boletim_servico import models


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('data-inicio', type=str)
        parser.add_argument('data-fim', type=str)
        parser.add_argument('periodicidade', choices=['diario', 'semanal', 'mensal'])
        parser.add_argument('--somente_documentos', action='store_true')

    def handle(self, *args, **options):
        inicio = datetime.strptime(options['data-inicio'], '%d/%m/%Y')
        fim = datetime.strptime(options['data-fim'], '%d/%m/%Y')
        periodicidade = options['periodicidade']
        somente_documentos = options['somente_documentos']
        if periodicidade == 'diario':
            while inicio <= fim:
                for boletim_programando in models.BoletimProgramado.objects.filter(programado=True):
                    boletim_programando.gerar_boletim_diario(inicio.date(), somente_documentos=somente_documentos)
                inicio += timedelta(days=1)
        elif periodicidade == 'semanal':
            while inicio <= fim:
                for boletim_programando in models.BoletimProgramado.objects.filter(programado_semanal=True):
                    boletim_programando.gerar_boletim_semanal(inicio.date(), somente_documentos=somente_documentos)
                inicio += timedelta(days=7)
        elif periodicidade == 'mensal':
            while inicio <= fim:
                for boletim_programando in models.BoletimProgramado.objects.filter(programado_mensal=True):
                    boletim_programando.gerar_boletim_mensal(inicio.date(), somente_documentos=somente_documentos)
                inicio += timedelta(days=30)
        else:
            print('Não existem boletins para gerar nas datas informadas')
