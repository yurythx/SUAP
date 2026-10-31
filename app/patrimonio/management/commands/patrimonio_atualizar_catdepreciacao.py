"""
Comando que deprecia todos os invenarios.
"""

import datetime

from django.db import transaction

from djtools.management.commands import BaseCommandPlus
from patrimonio.models import HistoricoCatDepreciacao
from patrimonio.relatorio import get_depreciacao_planocontabil_atual
from rh.models import UnidadeOrganizacional


class Command(BaseCommandPlus):
    @transaction.atomic
    def handle(self, *args, **options):
        hoje = datetime.date.today()
        print('\n Atualizando histórico de depreciação... \n')
        mes = hoje.month
        if hoje.month == 1:
            mes = 12
            ano = hoje.year - 1
        else:
            mes = hoje.month - 1
            ano = hoje.year
        dados = HistoricoCatDepreciacao.objects.filter(mes=mes, ano=ano)
        if not dados:
            for campus in UnidadeOrganizacional.objects.suap().all():
                get_depreciacao_planocontabil_atual(mes, ano, campus)
        print('\n FIM \n')
