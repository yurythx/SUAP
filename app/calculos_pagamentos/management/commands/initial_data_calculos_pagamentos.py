from django.core.management import call_command
from django.core.management.base import BaseCommand

__author__ = 'tassio'

"""
Procedimento / Arquivo feito por IFMA/Tássio em 16/08/2023
"""


class Command(BaseCommand):
    def handle(self, *args, **options):
        """
        Chama o comando loaddata para os arquivos de carga inicial da pasta fixtures
        USO:    python manage.py initial_data_calculos_pagamentos
        """

        call_command('loaddata', 'calculos_pagamentos/fixtures/initial_data_01_ValorPorFuncao.json')
        call_command('loaddata', 'calculos_pagamentos/fixtures/initial_data_02_NivelVencimento.json')
        call_command('loaddata', 'calculos_pagamentos/fixtures/initial_data_03_NivelVencimentoTAEPorClasseEPadrao.json')
        call_command('loaddata', 'calculos_pagamentos/fixtures/initial_data_04_ValorPorNivelVencimento.json')
        call_command('loaddata', 'calculos_pagamentos/fixtures/initial_data_05_ValorPorNivelVencimentoDocente.json')
        call_command('loaddata', 'calculos_pagamentos/fixtures/initial_data_06_ValorRetribuicaoTitulacao.json')
        call_command('loaddata', 'calculos_pagamentos/fixtures/initial_data_07_ValoresFuncaoDetalhados.json')
        call_command('loaddata', 'calculos_pagamentos/fixtures/initial_data_08_Sequencias_e_Rubricas.json')
        call_command('loaddata', 'calculos_pagamentos/fixtures/initial_data_09_ConfigPagamento.json')
        call_command('loaddata', 'calculos_pagamentos/fixtures/initial_data_10_ValorAlimentacao.json')
        call_command('loaddata', 'calculos_pagamentos/fixtures/initial_data_11_ValorAuxilioPreEscolar.json')
