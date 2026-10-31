from datetime import date, timedelta

from contratos.models import Contrato
from contratos.utils import Notificar
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        """
        Notifica os fiscais de contratos com exclusividade de mão de obra que ainda não possuem
        nenhum registro na aba Mão de Obra, 30 dias após o início do contrato.
        """
        hoje = date.today()
        data_limite = hoje - timedelta(days=30)

        contratos = Contrato.objects.filter(
            mao_obra_exclusiva=True,
            concluido=False,
            data_inicio__lte=data_limite,
            maosdeobra__isnull=True,
        ).distinct()

        for contrato in contratos:
            try:
                Notificar.contrato_sem_mao_de_obra(contrato)
            except Exception as e:
                self.stderr.write(f'Erro ao notificar contrato {contrato.id}: {e}')
