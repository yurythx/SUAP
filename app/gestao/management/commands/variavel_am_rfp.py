import datetime

from djtools.management.commands import BaseCommandPlus
from gestao.models import PeriodoReferencia, Variavel


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        print()
        print('- - - - -')
        print('Variáveis')
        print('- - - - -')
        print(
            'Ano de Referência: {} ({} à {})'.format(
                PeriodoReferencia.get_ano_referencia(),
                PeriodoReferencia.get_data_base().strftime('%d/%m/%Y'),
                PeriodoReferencia.get_data_limite().strftime('%d/%m/%Y'),
            )
        )
        print('Data da consulta: {}'.format(datetime.datetime.now().strftime('%d/%m/%Y - %H:%M')))
        print()

        am = Variavel.objects.get(sigla='AM')
        print(f'{am.sigla} ({am.nome}) = {am.get_valor_formatado()}')
        print(f'SQL: {am.get_querysets()[0].query}')

        print()
        print()

        rfp = Variavel.objects.get(sigla='RFP')
        print(f'{rfp.sigla} ({rfp.nome}) = {rfp.get_valor_formatado()}')
        print()

        faixas = [0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 1000]
        for index, _item in enumerate(faixas):
            if index > 0:
                qs = rfp.get_qs_renda_familiar(faixas[index - 1], faixas[index])
                print(f'Faixa de {faixas[index - 1]:.1f} a {faixas[index]:.1f}: {qs.count():d} ')

            if index == 7:
                print('SQL: {}')
