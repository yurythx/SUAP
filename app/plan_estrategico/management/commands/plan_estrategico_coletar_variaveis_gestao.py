"""
Comando que coleta valores atualizados das variaveis do gestão.
"""

import datetime

from django.db import transaction

from djtools.management.commands import BaseCommandPlus
from gestao.models import PeriodoReferencia
from gestao.models import Variavel as VariavelGestao
from plan_estrategico.models import PeriodoPreenchimentoVariavel, VariavelCampus, VariavelTrimestralCampus
from plan_estrategico.models import Variavel as VariavelPDI
from rh.models import UnidadeOrganizacional


class Command(BaseCommandPlus):
    @staticmethod
    def get_periodo_referencia_ano_atual(user=None):
        from gestao.models import PeriodoReferencia

        periodo_referencia = PeriodoReferencia()
        periodo_referencia.ano = datetime.date.today().year
        if PeriodoPreenchimentoVariavel.objects.filter(data_inicio__date=datetime.date.today()).exists():
            periodo_referencia.ano = PeriodoPreenchimentoVariavel.objects.filter(data_inicio__date=datetime.date.today()).first().ano.ano
        periodo_referencia.data_base = datetime.date(periodo_referencia.ano, 1, 1)
        periodo_referencia.data_limite = datetime.date(periodo_referencia.ano, 12, 31)
        return periodo_referencia

    PeriodoReferencia.get_referencia = get_periodo_referencia_ano_atual

    @transaction.atomic
    def handle(self, *args, **options):
        if PeriodoPreenchimentoVariavel.objects.filter(data_inicio__date=datetime.date.today()).exists():
            ano = PeriodoPreenchimentoVariavel.objects.filter(data_inicio__date=datetime.date.today()).first().ano.ano
            for variavelgestao in VariavelGestao.objects.all():
                try:
                    variavel_pdi = VariavelPDI.objects.get(sigla=variavelgestao.sigla)
                    for uo in UnidadeOrganizacional.objects.uo().all():
                        valor_var_gestao = variavelgestao.get_valor(uo=uo)
                        if VariavelCampus.objects.filter(variavel=variavel_pdi, uo=uo, ano=ano).exists():
                            variavel = VariavelCampus.objects.get(variavel=variavel_pdi, uo=uo, ano=ano)
                            variavel.valor_real = valor_var_gestao
                            variavel.data_atualizacao = datetime.datetime.now()
                            variavel.save()
                            trimestre = PeriodoPreenchimentoVariavel.objects.filter(data_inicio__date=datetime.date.today()).first().trimestre
                            variavel_trimestral = VariavelTrimestralCampus.objects.get_or_create(
                                variavel=variavel, ano=variavel.ano, trimestre=trimestre
                            )[0]
                            variavel_trimestral.valor = variavel.valor_real
                            variavel_trimestral.save()
                except VariavelPDI.DoesNotExist:
                    pass
            variaveis_RFP = ('RFP_faixa_1', 'RFP_faixa_2', 'RFP_faixa_3', 'RFP_faixa_4', 'RFP_faixa_5', 'RFP_faixa_6', 'RFP_faixa_7')
            for var in variaveis_RFP:
                for uo in UnidadeOrganizacional.objects.uo().all():
                    if var == 'RFP_faixa_1':
                        valor_var_rfp = variavelgestao.get_qs_renda_familiar(0, 0.5, uo).count()
                    if var == 'RFP_faixa_2':
                        valor_var_rfp = variavelgestao.get_qs_renda_familiar(0.5, 1.0, uo).count()
                    if var == 'RFP_faixa_3':
                        valor_var_rfp = variavelgestao.get_qs_renda_familiar(1.0, 1.5, uo).count()
                    if var == 'RFP_faixa_4':
                        valor_var_rfp = variavelgestao.get_qs_renda_familiar(1.5, 2.0, uo).count()
                    if var == 'RFP_faixa_5':
                        valor_var_rfp = variavelgestao.get_qs_renda_familiar(2.0, 2.5, uo).count()
                    if var == 'RFP_faixa_6':
                        valor_var_rfp = variavelgestao.get_qs_renda_familiar(2.5, 3.0, uo).count()
                    if var == 'RFP_faixa_7':
                        valor_var_rfp = variavelgestao.get_qs_renda_familiar(3.0, 10000, uo).count()
                    if VariavelCampus.objects.filter(variavel__sigla=var, uo=uo, ano=ano).exists():
                        variavel = VariavelCampus.objects.get(variavel__sigla=var, uo=uo, ano=ano)
                        variavel.valor_real = valor_var_rfp
                        variavel.data_atualizacao = datetime.datetime.now()
                        variavel.save()

                        trimestre = PeriodoPreenchimentoVariavel.objects.filter(data_inicio__date=datetime.date.today()).first().trimestre
                        variavel_trimestral = VariavelTrimestralCampus.objects.get_or_create(
                            variavel=variavel, ano=variavel.ano, trimestre=trimestre
                        )[0]
                        variavel_trimestral.valor = variavel.valor_real
                        variavel_trimestral.save()
            print('Váriáveis do Gestão Importadas')
