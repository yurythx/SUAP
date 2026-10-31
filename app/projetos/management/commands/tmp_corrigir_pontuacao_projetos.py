"""
Comando para gerar bolsas na aplicação AE
"""

from djtools.management.commands import BaseCommandPlus
from projetos.models import Avaliacao


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        for avaliacao in Avaliacao.objects.filter(projeto__edital__tipo_edital__in=('2', '3')):
            avaliacao.save()
