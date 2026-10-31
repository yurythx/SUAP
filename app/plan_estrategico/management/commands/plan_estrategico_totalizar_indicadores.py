"""
Comando que totaliza a quantidade de indicadores de cada status do farol de desempenho.
"""

from datetime import date

from django.db import transaction

from djtools.management.commands import BaseCommandPlus
from plan_estrategico.models import PDI, ObjetivoIndicador, PeriodoPreenchimentoVariavel, TotalizadorIndicador
from rh.models import UnidadeOrganizacional


class Command(BaseCommandPlus):
    def contabilizar_indicadores(self, pdi, uo, ano_base, indicadores, trimestre_atual):
        qtd_alcancado = 0
        qtd_parcialmente_alcancado = 0
        qtd_nao_alcancado = 0
        for obj in indicadores:
            pdi_indicador = obj.indicador
            if not pdi_indicador.verificar_variavel_real_vazia(uo, ano_base) or trimestre_atual == 1:
                pdi_indicador.indicador.valor_real = pdi_indicador.indicador.get_formula_valor(uo, ano_base)
            if not pdi_indicador.verificar_variavel_ideal_vazia(uo, ano_base):
                pdi_indicador.indicador.valor_meta = pdi_indicador.indicador.get_formula_valor_meta(uo, ano_base)
                if trimestre_atual == 1:
                    meta_tri = pdi_indicador.indicador.valor_meta / 4
                else:
                    meta_tri = (pdi_indicador.indicador.valor_meta / 4) * (trimestre_atual - 1)
                pdi_indicador.indicador.valor_meta = meta_tri
            if not pdi_indicador.verificar_variavel_real_vazia(uo, ano_base):
                status = pdi_indicador.get_status_farol(uo, ano_base)
                if status == 'Alcançado':
                    qtd_alcancado += 1
                elif status == 'Parcialmente':
                    qtd_parcialmente_alcancado += 1
                elif status == 'Não Alcançado':
                    qtd_nao_alcancado += 1
        # indicadores alcancados
        alcancado = TotalizadorIndicador.get_or_create(ano=ano_base, uo=uo, status=TotalizadorIndicador.INDICADOR_ALCANCADO)[0]
        alcancado.total_indicadores = qtd_alcancado
        alcancado.save()

        # indicadores parcialmente alcancados
        parcialmente_alcancado = TotalizadorIndicador.get_or_create(
            ano=ano_base, uo=uo, status=TotalizadorIndicador.INDICADOR_PARCIALMENTE_ALCANCADO
        )[0]
        parcialmente_alcancado.total_indicadores = qtd_parcialmente_alcancado
        parcialmente_alcancado.save()

        # indicadores não alcançados
        nao_alcancado = TotalizadorIndicador.get_or_create(ano=ano_base, uo=uo, status=TotalizadorIndicador.INDICADOR_NAO_ALCANCADO)[0]
        nao_alcancado.total_indicadores = qtd_nao_alcancado
        nao_alcancado.save()

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            pdi = PDI.objects.latest('id')
        except PDI.DoesNotExist:
            print('Nenhum indicador foi encontrado')
            return

        verbosity = options.get('verbosity', 3)
        ano_base = date.today().year
        trimestre_atual = int(date.today().month - 1) / 3 + 1
        if PeriodoPreenchimentoVariavel.objects.filter(data_inicio__date__gt=date.today(), ano__ano=ano_base, trimestre=1).exists():
            ano_base = ano_base - 1
            trimestre_atual = 4
        indicadores = ObjetivoIndicador.objects.filter(indicador__pdi=pdi).distinct('indicador')
        uo = None
        self.contabilizar_indicadores(pdi, uo, ano_base, indicadores, trimestre_atual)
        for uo in UnidadeOrganizacional.objects.uo().all():
            self.contabilizar_indicadores(pdi, uo, ano_base, indicadores, trimestre_atual)
        if verbosity:
            print('\n Indicadores Totalizados \n')
