from datetime import date, timedelta

from django.db import transaction

from djtools.management.commands import BaseCommandPlus
from plan_estrategico.models import IndicadorTrimestralCampus, PDIIndicador, PeriodoPreenchimentoVariavel, VariavelCampus
from rh.models import UnidadeOrganizacional


class Command(BaseCommandPlus):
    help = 'Comando que zera o valor trimestral de cada variável com cadastro manual e atualizar valores trimestrais dos indicadores'

    def add_arguments(self, parser):
        parser.add_argument('--ano', dest='ano_base', help='Ano base')
        parser.add_argument('--trimestre', dest='trimestre_base', help='Trimestre base')

    @transaction.atomic
    def handle(self, *args, **options):
        verbosity = options.get('verbosity', 3)
        ano_base = options.get('ano_base')
        trimestre_base = options.get('trimestre_base')
        if ano_base and trimestre_base:
            self.atualizar_indicadores(ano_base, trimestre_base)
            if verbosity:
                print('\n Indicadores Atualizados \n')
        else:
            hoje = date.today()
            dia_periodo = hoje - timedelta(days=1)
            if PeriodoPreenchimentoVariavel.objects.filter(data_termino__date=dia_periodo).exists():
                periodo = PeriodoPreenchimentoVariavel.objects.filter(data_termino__date=dia_periodo).first()
                trimestre = periodo.trimestre
                ano_periodo = periodo.ano
                for variavel in VariavelCampus.objects.filter(ano=ano_periodo.ano, variavel__fonte='Manual'):
                    variavel.valor_trimestral = None
                    variavel.save()

                self.atualizar_indicadores(ano_periodo.ano, trimestre)
            if verbosity:
                print('\n Variaveis trimestrais Zeradas e Indicadores Atualizados \n')

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
