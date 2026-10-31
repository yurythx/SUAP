from djtools.management.commands import BaseCommandPlus
from ponto.models import DebitoExternoCadastro, SaldoExterno

"""
    issue: https://gitlab.ifrn.edu.br/cosinf/suap/-/issues/10842

    Não é permitida a auto-validação em saldos externos e débitos externos já validados.

    Em 01/03/2024 (em dados locais):
        Saldos externos validados = 2630
        Débitos externos validados = 70
        Saldos externos validados com auto-validação = 2566 (quase todos)
        Débitos externos validados com auto-validação = 0 (aqui OK)

        Saída do comando "corrigir_auto_validacao":
            Saldos externos -> analisados .................: 2630
            Saldos externos -> com auto-validação .........: 2566
            Saldos externos -> validador alterado .........: 2564
            Saldos externos -> validador continua inválido.: 2
            ---> #2051 | Larissa Layerr Oliveira de Medeiros e Lima (1212064)
            ---> #2052 | Larissa Layerr Oliveira de Medeiros e Lima (1212064)
            Débitos externos -> analisados ................: 70
            Débitos externos -> com auto-validação ........: 0
            Débitos externos -> validador alterado ........: 0
            Débitos externos -> validador continua inválido: 0
            [2024-03-01 20:09:19] Command corrigir_auto_validacao OK in 0:02:19
"""


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        # saldos externos
        saldos_externos_total = 0
        saldos_externos_auto_validacao = 0
        saldos_externos_alterados = 0
        saldos_externos_falhados = []
        for saldo_externo in SaldoExterno.objects.filter(situacao=SaldoExterno.SITUACAO_VALIDADO):
            saldos_externos_total += 1
            # auto-validação?
            if saldo_externo.validador == saldo_externo.servidor:
                saldos_externos_auto_validacao += 1
                data_cadastro = saldo_externo.data_cadastro.date()
                validador_eh_reitor_na_data_cadastro = saldo_externo.validador.eh_reitor(data_cadastro)
                if not validador_eh_reitor_na_data_cadastro:
                    # usa o primeiro chefe da lista na data do cadastro
                    chefes = saldo_externo.servidor.get_chefes_no_periodo(data_cadastro, data_cadastro).get(data_cadastro)
                    validador_na_data_cadastro = chefes[0] if chefes else None
                    if validador_na_data_cadastro:
                        # auto-validação resolvida?
                        if validador_na_data_cadastro != saldo_externo.servidor:
                            saldo_externo.validador = validador_na_data_cadastro
                            saldo_externo.save()
                            print(f'Saldo Externo: #{saldo_externo.id} | {saldo_externo.servidor} ... OK')
                            saldos_externos_alterados += 1
                        else:
                            saldos_externos_falhados.append(saldo_externo)
                    else:
                        saldos_externos_falhados.append(saldo_externo)

        # debitos externos
        debitos_externos_total = 0
        debitos_externos_auto_validacao = 0
        debitos_externos_alterados = 0
        debitos_externos_falhados = []
        for debito_externo in DebitoExternoCadastro.objects.filter(situacao=DebitoExternoCadastro.SITUACAO_VALIDADO):
            debitos_externos_total += 1
            # auto-validação?
            if debito_externo.validador == debito_externo.servidor:
                debitos_externos_auto_validacao += 1
                data_cadastro = debito_externo.data_cadastro.date()
                validador_eh_reitor_na_data_cadastro = debito_externo.validador.eh_reitor(data_cadastro)
                if not validador_eh_reitor_na_data_cadastro:
                    # usa o primeiro chefe da lista na data do cadastro
                    chefes = debito_externo.servidor.get_chefes_no_periodo(data_cadastro, data_cadastro).get(data_cadastro)
                    validador_na_data_cadastro = chefes[0] if chefes else None
                    if validador_na_data_cadastro:
                        # auto-validação resolvida?
                        if validador_na_data_cadastro != debito_externo.servidor:
                            debito_externo.validador = validador_na_data_cadastro
                            debito_externo.save()
                            print(f'Débito Externo: #{debito_externo.id} | {debito_externo.servidor} ... OK')
                            debitos_externos_alterados += 1
                        else:
                            debitos_externos_falhados.append(debito_externo)
                    else:
                        debitos_externos_falhados.append(debito_externo)

        print(f'Saldos externos -> analisados .................: {saldos_externos_total}')
        print(f'Saldos externos -> com auto-validação .........: {saldos_externos_auto_validacao}')
        print(f'Saldos externos -> validador alterado .........: {saldos_externos_alterados}')
        print(f'Saldos externos -> validador continua inválido.: {len(saldos_externos_falhados)}')
        for _ in saldos_externos_falhados:
            print(f'---> #{_.id} | {_.servidor}')

        print(f'Débitos externos -> analisados ................: {debitos_externos_total}')
        print(f'Débitos externos -> com auto-validação ........: {debitos_externos_auto_validacao}')
        print(f'Débitos externos -> validador alterado ........: {debitos_externos_alterados}')
        print(f'Débitos externos -> validador continua inválido: {len(debitos_externos_falhados)}')
        for _ in debitos_externos_falhados:
            print(f'---> #{_.id} | {_.servidor}')
