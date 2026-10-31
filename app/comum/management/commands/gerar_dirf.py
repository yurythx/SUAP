import pandas as pd

from djtools.management.commands import BaseCommandPlus
from djtools.utils import cpf_valido


class Command(BaseCommandPlus):
    help = 'Gerar os arquivos DIRFs de cada campus de acordo com planilha recebida'

    def add_arguments(self, parser):
        # Positional arguments
        parser.add_argument('planilha', type=str, help='Planilha com os dados')
        parser.add_argument('dirfs', type=str, help='Local onde os arquivos DIRFs vão ser gerados')

    def handle(self, *args, **options):
        planilha = options['planilha']
        dirfs = options['dirfs']
        self.gerar_dirf(planilha, dirfs)

    def gerar_dirf(self, planilha, dirfs):
        RTRT = 'RTRT'
        RTPO = 'RTPO'
        RTIRF = 'RTIRF'
        RIO = 'RIO'

        DIRF = 'DIRF'
        RESPO = 'RESPO'
        DECPJ = 'DECPJ'
        IDREC = 'IDREC'

        def get_valor(row, numero_celula):
            return row.iloc[numero_celula]

        def add_valor(valor, file):
            if valor == '' or valor == 0.0 or pd.isna(valor):
                valor = ''
            else:
                valor = f'{valor:.2f}'.replace('.', '')

            file.write(f'{valor}|')

        # Read both sheets
        df_sheet0 = pd.read_excel(planilha, sheet_name=0)
        df_sheet1 = pd.read_excel(planilha, sheet_name=1)

        siafi = {}

        # Process first sheet
        for _i, row in df_sheet0.iterrows():
            nome_campus = str(get_valor(row, 16)).strip()
            cnpj_campus = int(get_valor(row, 15))

            siafi[cnpj_campus] = {}
            siafi[cnpj_campus]['cnpj'] = cnpj_campus
            siafi[cnpj_campus]['nome'] = nome_campus
            siafi[cnpj_campus][IDREC] = {}

            dirf = {}
            dirf['ano_referencia'] = int(get_valor(row, 1))
            dirf['ano_calendario'] = int(get_valor(row, 2))
            dirf['identificador_retificadora'] = get_valor(row, 3)
            dirf['numero_recibo'] = get_valor(row, 4)
            dirf['identificador_estrutura_layout'] = get_valor(row, 5)
            siafi[cnpj_campus][DIRF] = dirf

            respo = {}
            respo['cpf'] = int(get_valor(row, 7))
            respo['nome'] = get_valor(row, 8)
            respo['ddd'] = int(get_valor(row, 9))
            respo['telefone'] = int(get_valor(row, 10))
            respo['ramal'] = int(get_valor(row, 11))
            respo['fax'] = int(get_valor(row, 12))
            respo['correio_eletronico'] = get_valor(row, 13)
            siafi[cnpj_campus][RESPO] = respo

            decpj = {}
            decpj['cnpj'] = cnpj_campus
            decpj['nome_empresarial'] = nome_campus
            decpj['natureza_declarante'] = int(get_valor(row, 17))
            decpj['cpf_responsavel_cnpj'] = get_valor(row, 18)
            decpj['isorscp'] = get_valor(row, 19)
            decpj['iddcddj'] = get_valor(row, 20)
            decpj['idiaifci'] = get_valor(row, 21)
            decpj['idrprde'] = get_valor(row, 22)
            decpj['ippas'] = get_valor(row, 23)
            decpj['iprjojp'] = get_valor(row, 24)
            decpj['ieudmcssvrrtnoreos'] = get_valor(row, 25)
            decpj['ised'] = get_valor(row, 26)
            decpj['data_evento'] = get_valor(row, 27)
            siafi[cnpj_campus][DECPJ] = decpj

        # Process second sheet
        inconsistencias = []
        for i, row in df_sheet1.iterrows():
            cnpj_campus = int(get_valor(row, 1))
            idrec_codigo_receita = get_valor(row, 3)
            idrec = siafi[cnpj_campus][IDREC]
            if idrec_codigo_receita not in idrec:
                idrec[idrec_codigo_receita] = {}
                idrec[idrec_codigo_receita]['declarantes'] = {}

            declarantes = idrec[idrec_codigo_receita]['declarantes']
            cpf = get_valor(row, 5)
            if isinstance(cpf, str):
                cpf = cpf.replace('-', '').replace('.', '')
            cpf = f'{int(cpf):011d}'
            nome = str(get_valor(row, 6)).replace('.', ' ')

            declarante = {}
            declarante['nome'] = nome
            declarante['cpf'] = cpf
            self.cpf = cpf

            rtrt = get_valor(row, 10)
            if rtrt == RTRT:
                rtrt = {}
                rtrt['valores'] = [get_valor(row, i) for i in range(11, 24)]
                declarante[RTRT] = rtrt

            rtpo = get_valor(row, 24)
            if rtpo == RTPO:
                rtpo = {}
                rtpo['valores'] = [get_valor(row, i) for i in range(25, 38)]
                declarante[RTPO] = rtpo

            rtirf = get_valor(row, 38)
            if rtirf == RTIRF:
                rtirf = {}
                rtirf['valores'] = [get_valor(row, i) for i in range(39, 52)]
                declarante[RTIRF] = rtirf

            rio = get_valor(row, 52)
            if rio == RIO:
                rio = {}
                rio['valor'] = get_valor(row, 53)
                rio['descricao'] = get_valor(row, 54)
                declarante[RIO] = rio

            declarantes[cpf] = declarante
            if not cpf_valido(cpf):
                inconsistencias.append(f'{cpf} {nome}')

        import subprocess

        # Não tem o cadastro dos CNPJs no SUAP
        for cnpj_campus, siafi_campus in list(siafi.items()):
            ug = cnpj_campus
            if ug == 10877412000591:
                ug = 'AP'
            elif ug == 10877412001210:
                ug = 'CA'
            elif ug == 10877412001300:
                ug = 'CAL'
            elif ug == 10877412001806:
                ug = 'CANG'
            elif ug == 10877412001997:
                ug = 'CM'
            elif ug == 10877412001130:
                ug = 'CN'
            elif ug == 10877412001059:
                ug = 'CNAT'
            elif ug == 10877412000320:
                ug = 'IP'
            elif ug == 10877412000834:
                ug = 'JC'
            # elif ug == u'':
            #     ug = u'JUC'
            # elif ug == u'':
            #     ug = u'LAJ'
            elif ug == 10877412000753:
                ug = 'MC'
            elif ug == 10877412000400:
                ug = 'MO'
            elif ug == 10877412001563:
                ug = 'NC'
            # elif ug == u'':
            #     ug = u'PAAS'
            elif ug == 10877412001482:
                ug = 'PAR'
            elif ug == 10877412000672:
                ug = 'PF'
            elif ug == 10877412000249:
                ug = 'SC'
            elif ug == 10877412001644:
                ug = 'SGA'
            elif ug == 10877412001725:
                ug = 'SPO'
            # elif ug == 10877412001059: # igual ao do CNAT
            #     ug = u'ZL'
            elif ug == 10877412000915:
                ug = 'ZN'
            elif ug == 10877412000168:
                ug = 'RE'

            caminho_arquivo = f'{dirfs}/dirf_{ug}.txt'
            f = open('/tmp/dirf_temp', 'w')

            dirf = siafi_campus[DIRF]
            f.write(
                'DIRF|{}|{}|{}|{}|{}|\n'.format(
                    dirf['ano_referencia'],
                    dirf['ano_calendario'],
                    dirf['identificador_retificadora'],
                    dirf['numero_recibo'],
                    dirf['identificador_estrutura_layout'],
                )
            )

            respo = siafi_campus[RESPO]
            f.write('RESPO|{}|{}|{}|{}|{}|{}||\n'.format(respo['cpf'], respo['nome'], respo['ddd'], respo['telefone'], respo['ramal'], respo['fax']))

            decpj = siafi_campus[DECPJ]
            f.write(
                'DECPJ|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|\n'.format(
                    decpj['cnpj'],
                    decpj['nome_empresarial'],
                    decpj['natureza_declarante'],
                    decpj['cpf_responsavel_cnpj'],
                    decpj['isorscp'],
                    decpj['iddcddj'],
                    decpj['idiaifci'],
                    decpj['idrprde'],
                    decpj['ippas'],
                    decpj['iprjojp'],
                    decpj['ieudmcssvrrtnoreos'],
                    decpj['ised'],
                    decpj['data_evento'],
                )
            )
            for codigo_receita in sorted(siafi_campus[IDREC].keys()):
                dados = siafi_campus[IDREC][codigo_receita]
                f.write(f'IDREC|{int(codigo_receita):04}|\n')
                declarantes = dados['declarantes']
                cpfs = list(declarantes.keys())
                for cpf in sorted(cpfs):
                    declarante = declarantes[cpf]
                    f.write('BPFDEC|{:011d}|{}||N|N|\n'.format(int(cpf.replace('-', '')), declarante['nome'][:60]))
                    if RTRT in declarante:
                        f.write('RTRT|')
                        for valor in declarante[RTRT]['valores']:
                            add_valor(valor, f)
                        f.write('\n')

                    if RTPO in declarante:
                        f.write('RTPO|')
                        for valor in declarante[RTPO]['valores']:
                            add_valor(valor, f)
                        f.write('\n')

                    if RTIRF in declarante:
                        f.write('RTIRF|')
                        for valor in declarante[RTIRF]['valores']:
                            add_valor(valor, f)
                        f.write('\n')

                    if RIO in declarante:
                        f.write('RIO|')
                        add_valor(declarante[RIO]['valor'], f)
                        f.write('{}|'.format(declarante[RIO]['descricao']))
                        f.write('\n')

            f.write('FIMDIRF|')
            f.close()
            temp = open(caminho_arquivo, 'w')
            args = ['iconv', '--from-code=UTF-8', '--to-code=ISO-8859-1', f.name]
            subprocess.call(args, stdout=temp)
            temp.close()
