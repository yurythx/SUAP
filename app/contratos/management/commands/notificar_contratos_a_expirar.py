from datetime import datetime

from contratos.models import Contrato
from contratos.utils import Notificar
from djtools.management.commands import BaseCommandPlus

"""
python manage.py notificar_contratos_a_expirar
"""


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        """
        A seguinte notificação abaixo deverá ser enviada para todos os Fiscais do Contrato ativos
        a 45, 30 e 15 de expiração de contratos não concluídos:
        """
        # Envia notificações, cancelado=False
        contratos_a_notificar = Contrato.objects.filter(concluido=False, cancelado=False)

        print(f'{contratos_a_notificar.count()} contratos para notificar!')
        hoje = datetime.now().date()
        for contrato in contratos_a_notificar:
            try:
                dias = (contrato.get_data_fim() - hoje).days
                if dias in [15, 30, 45]:
                    print(f'Contrato {contrato.numero} / Data Fim: {contrato.get_data_fim()} / Expira em {dias} dias.')
                    Notificar.contrato_a_expirar(contrato, dias)
            except Exception:
                continue
