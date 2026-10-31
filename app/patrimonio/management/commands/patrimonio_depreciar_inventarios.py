"""
Comando que deprecia todos os inventários.
"""

import datetime

import tqdm
from django.core.cache import cache

from djtools.management.commands import BaseCommandPlus
from patrimonio.models import Inventario, InventarioValor
from patrimonio.relatorio import get_depreciacao_planocontabil_atual
from rh.models import UnidadeOrganizacional


class Command(BaseCommandPlus):
    def handle(self, *args: object, **options: object) -> None:
        hoje = datetime.date.today()
        inventarios_depreciados = InventarioValor.objects.filter(data_operacao__month=hoje.month, data_operacao__year=hoje.year).values_list(
            'inventario__id', flat=True
        )
        qs = Inventario.depreciaveis.com_vida_util().exclude(entrada_permanente__categoria__codigo__in=('00', '05', '9907'))
        qs = qs.exclude(id__in=inventarios_depreciados)

        for inventario in tqdm.tqdm(qs):
            InventarioValor.depreciar(inventario)

        self.stdout.write('\n Atualizando histórico de depreciação... \n')
        mes = hoje.month - 1
        ano = hoje.year
        if hoje.month == 1:
            mes = 12
            ano = hoje.year - 1

        cache.delete('inventarios_inconsistente_ids')
        for campus in UnidadeOrganizacional.objects.suap().all():
            get_depreciacao_planocontabil_atual(mes, ano, campus)
        self.stdout.write('\n FIM \n')
