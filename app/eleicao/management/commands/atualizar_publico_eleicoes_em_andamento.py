"""
Comando para atualizar os públicos das enquetes em andamento
"""

from djtools.management.commands import BaseCommandPlus
from eleicao.models import Eleicao


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        for eleicao in Eleicao.get_abertas():
            eleicao.save()
