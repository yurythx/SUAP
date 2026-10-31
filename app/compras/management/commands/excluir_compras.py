from compras.models import Compra, EtapaCompra
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    help = 'Exclui todos os processos de compras e etapas relacionadas.'

    def handle(self, *args, **options):
        total_compras = Compra.objects.count()
        total_etapas = EtapaCompra.objects.count()
        Compra.objects.all().delete()  # Cascade deletes EtapaCompra
        self.stdout.write(self.style.SUCCESS(f'Excluiu {total_compras} processos de compras e {total_etapas} etapas relacionadas.'))
