from django.db import transaction

from djtools.management.commands import BaseCommandPlus
from plan_estrategico.models import IndicadorTrimestralCampus, PDIIndicador, PeriodoPreenchimentoVariavel
from rh.models import UnidadeOrganizacional


class Command(BaseCommandPlus):
    help = 'Comando que atualiza o valor trimestral do indicador durante o período de preenchimento'

    @transaction.atomic
    def handle(self, *args, **options):
        verbosity = options.get('verbosity', 3)
        if PeriodoPreenchimentoVariavel.get_em_periodo_de_preenchimento():
            periodo = PeriodoPreenchimentoVariavel.get_em_periodo_de_preenchimento()[0]
            trimestre = periodo.trimestre
            ano_periodo = periodo.ano
            self.atualizar_indicadores(ano_periodo.ano, trimestre)
        if verbosity:
            print('\n Valores Trimestrais dos Indicadores Atualizados \n')

    def atualizar_indicadores(self, ano_base, trimestre):
        indicadores = PDIIndicador.objects.all()
        for indicador in indicadores:
            for uo in UnidadeOrganizacional.objects.uo():
                indicadorTrimestral = IndicadorTrimestralCampus.objects.get_or_create(indicador=indicador, ano=ano_base, trimestre=trimestre, uo=uo)[
                    0
                ]
                indicadorTrimestral.valor = indicador.indicador.get_formula_valor(uo=uo, ano_base=ano_base)
                indicadorTrimestral.save()

            indicadorTrimestral_global = IndicadorTrimestralCampus.objects.get_or_create(
                indicador=indicador, ano=ano_base, trimestre=trimestre, uo=None
            )[0]
            indicadorTrimestral_global.valor = indicador.indicador.get_formula_valor(uo=None, ano_base=ano_base)
            indicadorTrimestral_global.save()
