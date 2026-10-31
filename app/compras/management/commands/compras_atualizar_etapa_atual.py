from datetime import datetime

from compras.models import Compra, EtapaCompra
from djtools.management.commands import BaseCommandPlus

"""
python manage.py compras_atualizar_etapa_atual
"""


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        try:
            """Obtém todas as compras não finalizadas"""
            etapas_compras_vigentes = EtapaCompra.objects.filter(data_inicio__lte=datetime.today(), data_fim__gte=datetime.today())

            """Obtém todas as compras e checa se a etapa atual está igual a etapa vigente, caso contrário, atualiza a etapa atual"""
            qtd_compras_atualizadas = 0
            if etapas_compras_vigentes:
                for compra in Compra.objects.all():
                    etapa_compra_vigente = etapas_compras_vigentes.filter(compra=compra).first()
                    if etapa_compra_vigente and compra.etapa_atual != etapa_compra_vigente.etapa:
                        compra.atualizar_etapa_atual()
                        qtd_compras_atualizadas += 1
            else:
                self.stdout.write(self.style.SUCCESS('Não existem compras com etapas vigentes para atualização.'))

            self.stdout.write(self.style.SUCCESS(f'Atualizou {qtd_compras_atualizadas} compras. '))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Erro na execução, detalhes: {e}'))
