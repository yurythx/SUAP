from almoxarifado.models import MaterialConsumo, RequisicaoAlmoxUserMaterial
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        qs = MaterialConsumo.objects.filter(movimentoalmoxentrada__isnull=True, movimentoalmoxsaida__isnull=True, empenhoconsumo__isnull=True)

        ids = [str(i) for i in qs.values_list('id', flat=True)]

        if ids:
            for i in RequisicaoAlmoxUserMaterial.objects.filter(material__id__in=ids):
                if i.can_delete():
                    i.delete()
            qs.delete()
        print(self.style.SQL_COLTYPE(f'{len(ids)} materiais removidos'))
