"""
Comando que coleta valores atualizados das variaveis do tesouro gerencial.
"""

import datetime

from django.db import transaction

from djtools.management.commands import BaseCommandPlus
from plan_estrategico.models import PeriodoPreenchimentoVariavel, VariavelCampus, VariavelTrimestralCampus
from plan_estrategico.models import Variavel as VariavelPDI
from rh.models import UnidadeOrganizacional
from tesouro_gerencial.models import Variavel as VariavelTesouro


class Command(BaseCommandPlus):
    @transaction.atomic
    def handle(self, *args, **options):
        if PeriodoPreenchimentoVariavel.objects.filter(data_inicio__date=datetime.date.today()).exists():
            ano = PeriodoPreenchimentoVariavel.objects.filter(data_inicio__date=datetime.date.today()).first().ano.ano
            funcoes = {}
            funcoes['DEST_EXEC'] = 'get_DEST_EXEC'
            funcoes['LOA_EXEC'] = 'get_LOA_EXEC'
            funcoes['RECCAPT'] = 'get_RECCAPT'
            funcoes['20RL_LOA'] = 'get_20RL_LOA'
            funcoes['GCC'] = 'get_GCC'
            funcoes['GTO_LOA'] = 'get_GTO_LOA'
            funcoes['fGPE'] = 'get_fGPE'
            funcoes['fGTO'] = 'get_fGTO'
            funcoes['fGOC'] = 'get_fGOC'
            funcoes['fGCI'] = 'get_fGCI'
            funcoes['fGCO'] = 'get_fGCO'
            for nome_variavel, funcao in funcoes.items():
                variavel_pdi = VariavelPDI.objects.get(sigla=nome_variavel)
                for uo in UnidadeOrganizacional.objects.uo():
                    valor_variavel = getattr(VariavelTesouro, funcao)(uo, ano)
                    if VariavelCampus.objects.filter(variavel=variavel_pdi, uo=uo, ano=ano).exists():
                        variavel = VariavelCampus.objects.get(variavel=variavel_pdi, uo=uo, ano=ano)
                        variavel.valor_real = valor_variavel
                        variavel.data_atualizacao = datetime.datetime.now()
                        variavel.save()
                        trimestre = PeriodoPreenchimentoVariavel.objects.filter(data_inicio__date=datetime.date.today()).first().trimestre
                        variavel_trimestral = VariavelTrimestralCampus.objects.get_or_create(
                            variavel=variavel, ano=variavel.ano, trimestre=trimestre
                        )[0]
                        variavel_trimestral.valor = variavel.valor_real
                        variavel_trimestral.save()
            print('Váriáveis do Tesouro Gerencial Importadas')
