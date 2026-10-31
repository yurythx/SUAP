from djtools.management.commands import BaseCommandPlus
from ponto.models import RecessoOpcao, RecessoOpcaoEscolhida

"""
    Compensações em Acompanhamento - Recesso de Natal/Ano Novo - Validação: Autorizado
    Corrigir Dias Efetivos a Compensar
"""


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        print('Compensações em Acompanhamento - Recesso de Natal/Ano Novo - Validação: Autorizado')

        print('----------------------------------------------------------')
        print('Corrigindo Dias Efetivos a Compensar')

        qtd = 0
        qtd_erro = 0
        for acompanhamento in RecessoOpcaoEscolhida.objects.filter(
            recesso_opcao__tipo=RecessoOpcao.TIPO_PERMITE_ESCOLHA_LIVRE, validacao=RecessoOpcaoEscolhida.VALIDACAO_AUTORIZADO
        ):
            try:
                acompanhamento.dias_efetivos_a_compensar(force_update=True)
            except Exception:
                qtd_erro += 1
            qtd += 1

        print(f'Total de Acompanhamentos: {qtd}')
        print(f'Erros: {qtd_erro}')
