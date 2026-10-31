"""
Comando que coleta valores atualizados das variaveis após o periodo de preenchimento
"""

import datetime
from datetime import date, timedelta

from django.db import transaction

from djtools.management.commands import BaseCommandPlus
from plan_estrategico.models import PeriodoPreenchimentoVariavel, VariavelCampus, VariavelTrimestralCampus
from rh.models import UnidadeOrganizacional


class Command(BaseCommandPlus):
    @transaction.atomic
    def handle(self, *args, **options):
        dia_periodo = date.today() - timedelta(days=1)
        if PeriodoPreenchimentoVariavel.objects.filter(data_termino__date=dia_periodo).exists():
            ano = PeriodoPreenchimentoVariavel.objects.filter(data_termino__date=dia_periodo).first().ano.ano
            for uo in UnidadeOrganizacional.objects.uo().all():
                variaveis = ('MI_E1', 'UNID')
                for var in variaveis:
                    total = 0
                    if var == 'MI_E1':
                        MI_disc = VariavelCampus.objects.filter(variavel__sigla='MI_disc', uo=uo, ano=ano).first()
                        MI_disc = MI_disc and MI_disc.valor_real or 0
                        MI_serv = VariavelCampus.objects.filter(variavel__sigla='MI_serv', uo=uo, ano=ano).first()
                        MI_serv = MI_serv and MI_serv.valor_real or 0
                        total = MI_disc + MI_serv

                    if var == 'UNID':
                        total = 1
                    variavel = VariavelCampus.objects.filter(variavel__sigla=var, uo=uo, ano=ano).first()
                    if variavel:
                        variavel.valor_real = total
                        variavel.data_atualizacao = datetime.datetime.now()
                        variavel.save()
                        periodo = PeriodoPreenchimentoVariavel.objects.filter(data_termino__date=dia_periodo).first()
                        if periodo:
                            variavel_trimestral = VariavelTrimestralCampus.objects.get_or_create(
                                variavel=variavel, ano=variavel.ano, trimestre=periodo.trimestre
                            )[0]
                            variavel_trimestral.valor = variavel.valor_real
                            variavel_trimestral.save()

            print('Váriáveis Importadas')
