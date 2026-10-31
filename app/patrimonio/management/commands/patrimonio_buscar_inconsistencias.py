"""
Comando que verificar todos os inventários depreciáveis por inconsistência de valores.
"""

import datetime

import tqdm

from djtools.management.commands import BaseCommandPlus
from patrimonio.models import Inventario, InventarioValor
from decimal import Decimal
import traceback
from dateutil.relativedelta import relativedelta


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        hoje = datetime.date.today()
        inventarios_depreciados = InventarioValor.objects.filter(data_operacao__month=hoje.month, data_operacao__year=hoje.year).values_list(
            'inventario__id', flat=True
        )
        qs = Inventario.depreciaveis.all().exclude(entrada_permanente__categoria__codigo__in=('00', '05', '9907', '99', '87', '93', '2'))
        qs = qs.exclude(id__in=inventarios_depreciados)

        inventarios_inconsistentes = []
        for inventario in tqdm.tqdm(qs):
            try:
                hoje = datetime.date.today().replace(day=1)
                ultimo_dia_mes_anterior = hoje - datetime.timedelta(days=1)
                vida_util_em_anos = inventario.entrada_permanente.categoria.vida_util_em_anos
                fim_da_vida_ultil = inventario.entrada_permanente.entrada.data.date() + relativedelta(years=vida_util_em_anos)
                # Inventários já totalmente depreciados, ou seja, o valor atual deve ser igual ao valor residual.
                if fim_da_vida_ultil < ultimo_dia_mes_anterior:
                    percentual_residual_do_inventario = inventario.entrada_permanente.categoria.percentual_residual
                    valor_entrada = inventario.entrada_permanente.valor
                    valor_residual = Decimal('%.2f' % (float(valor_entrada) * percentual_residual_do_inventario))
                    if inventario.valor > valor_residual:
                        inventario_inconsistente = {
                            'inventario_numero': inventario.numero,
                            'data_entrada': inventario.entrada_permanente.entrada.data.date(),
                            'valor_residual_previsto': valor_residual,
                            'valor_atual': inventario.valor,
                            'depreciacoes_previstas': vida_util_em_anos * 12,
                            'depreciacoes_atuais': len(inventario.inventariovalor_set.all()),
                        }
                        print(f'{inventario_inconsistente}')
                        inventarios_inconsistentes.append(inventario_inconsistente)
                # InventarioValor.depreciar(inventario)
            except Exception:
                traceback.print_exc()
                print(f'Erro ao depreciar inventário: {inventario}')
                break

        print(f'Inventários inconsistentes: {len(inventarios_inconsistentes)}')
