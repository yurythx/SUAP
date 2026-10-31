from datetime import date, timedelta

from contratos.models import Agenda
from contratos.utils import Notificar
from djtools.management.commands import BaseCommandPlus

"""
python manage.py notificar_fiscalizacao_contratos

Conforme requisito da Demanda: #1609
https://suap.ifrn.edu.br/demandas/visualizar/1609/

"""


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Iniciando comando para notificar aos fiscais que existem contratos a serem fiscalizados.'))
        hoje = date.today()
        datas = [hoje, hoje - timedelta(days=15), hoje - timedelta(days=30)]
        agendas = Agenda.objects.filter(data_prevista__in=datas, data_execucao__isnull=True)
        for agenda in agendas:
            Notificar.contratos_a_serem_fiscalizados(agenda)
            self.stdout.write(self.style.SUCCESS(f'Email enviado para Agenda ID {agenda.id}.'))

        self.stdout.write(self.style.SUCCESS('Finalizando comando para notificar aos fiscais que existem contratos a serem fiscalizados.'))
