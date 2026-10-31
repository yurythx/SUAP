"""
Comando que reavalia todos os invenarios.
"""

import sys

from django.utils import termcolors

from djtools.management.commands import BaseCommandPlus
from patrimonio.models import Inventario, InventarioReavaliacao


class Command(BaseCommandPlus):
    def handle(self, *args: object, **options: object) -> None:
        inventarios = Inventario.depreciaveis.com_vida_util()
        total = inventarios.count()
        count = 1
        for inventario in inventarios:
            porcentagem = int(float(count) / total * 100)
            sys.stdout.write(termcolors.make_style(fg='cyan', opts=('bold',))(f'\r {porcentagem}% - Reavaliando {count} de {total}'))
            sys.stdout.flush()
            count += 1

            InventarioReavaliacao.reavaliar(inventario)

        self.stdout.write('\n FIM \n')
