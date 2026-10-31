"""
Comando para gerar bolsas na aplicação AE
"""

from djtools.management.commands import BaseCommandPlus
from projetos.models import Participacao


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        """
        :param args: lista de ids de editais
        :param options:
        :return:
        """
        print('GERACAO BOLSA AE ...')
        editais_ids = args
        Participacao.gerar_bolsa_ae(editais_ids)
