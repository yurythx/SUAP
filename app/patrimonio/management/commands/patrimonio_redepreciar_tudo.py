"""
Comando que reavalia todos os invenarios.
"""

import sys
import datetime
from django.utils import termcolors
from django.core.cache import cache
from patrimonio.relatorio import get_depreciacao_planocontabil_atual
from rh.models import UnidadeOrganizacional
from djtools.management.commands import BaseCommandPlus
from patrimonio.models import Inventario, InventarioValor


class Command(BaseCommandPlus):
    def handle(self, *args: object, **options: object) -> None:
        hoje = datetime.date.today()
        total = Inventario.depreciaveis.count()
        count = 1
        inventarios = Inventario.depreciaveis.all().exclude(entrada_permanente__categoria__codigo__in=('00', '05', '9907', '99', '87', '93', '2'))
        for inventario in inventarios:
            porcentagem = int(float(count) / total * 100)
            inventario.inventariovalor_set.all().delete()
            inventario.valor = inventario.entrada_permanente.valor
            inventario.save()
            if inventario.entrada_permanente.categoria.vida_util_em_anos > 0:
                InventarioValor.depreciar(inventario)
            sys.stdout.write(termcolors.make_style(fg='cyan', opts=('bold',))(f'\r {porcentagem}% - Realizando nova depreciação {count} de {total}'))
            sys.stdout.flush()
            count += 1

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
