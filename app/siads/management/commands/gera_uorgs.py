from datetime import datetime

from tqdm import tqdm

from djtools.management.commands import BaseCommandPlus
from rh.models import Funcao, ServidorFuncaoHistorico, Setor
from siads.utils import DELIMITADOR, FIM_LINHA, trim


class Command(BaseCommandPlus):
    def get_chefe(self, setor):
        ServidorFuncaoHistorico.objects.atuais().filter(setor=setor, codigo__in=[Funcao.CODIGO_CD, Funcao.CODIGO_FG])

    def cabecalho(self, fd=None):
        dados = []
        # Montagem do registro
        dados.append('H')  # Identificador da linha
        dados.append('UO')  # Tipo do Arquivo
        dados.append('1')  # Sequencial que identifica o número do arquivo
        dados.append('25000')  # Código do órgão implantador
        dados.append('170531')  # Código da UASG
        dados.append('03063892408')  # CPF do usuário que gerou o arquivo
        dados.append(FIM_LINHA)  # Finalizador de linha

        row = DELIMITADOR.join(dados)

        if fd is not None:
            fd.write(f'{row}\n')
        else:
            return row

    def add_registro(self, setor, fd=None):
        uo = setor.uo.equivalente
        dados = []

        # self.get_chefe(setor=setor)

        # Montagem do registro
        dados.append('D')  # Identificador da linha
        dados.append(trim(setor.codigo, 100))  # Código da UORG - A(100)
        dados.append(uo.codigo_ug)  # Código da UG Vinculada - N(6)
        dados.append(trim(setor.nome, 100))  # Nome da UORG - A(100)
        dados.append(trim(setor.sigla, 16))  # Sigla da UORG - A(16)
        dados.append(trim('', 60))  # Endereço da UORG - A(60)
        dados.append(trim('', 8))  # CEP da UORG - A(8)
        dados.append(trim('', 4))  # DDD da UORG - A(4)
        dados.append(trim('', 8))  # Telefone da UORG - A(8)
        dados.append(trim('', 4))  # Ramal da UORG - A(4)
        dados.append(trim('', 14))  # Fax da UORG - A(14)
        dados.append(trim('', 11))  # CPF do Responsável pela UORG - N(11)
        dados.append(trim('', 40))  # Nome do Responsável pela UORG - A(40)
        dados.append(trim('', 12))  # Matrícula SIAPE do Responsável pela UORG - N(12)
        dados.append(trim('', 25))  # Número da Portaria de Nomeação do responsável pela UORG - A(25)
        dados.append(trim('', 100))  # Código da UORG Subordinada - A(100)
        dados.append(trim('', 40))  # Nome Reduzido - A(40)
        dados.append(trim('', 8))  # Data da Criação (DDMMYYYY) - N(8)
        dados.append(trim('', 60))  # Número do Documento de Criação - A(60)
        dados.append(trim('', 2))  # Sigla da UF - A(2)
        dados.append(trim('', 40))  # Municipio - A(40)
        dados.append(trim('', 50))  # E-Mail - A(50)

        dados.append(FIM_LINHA)  # Finalizador de linha

        row = DELIMITADOR.join(dados)

        if fd is not None:
            fd.write(f'{row}\n')
        else:
            return row

    def del_registro(self, uo, fd=None):
        dados = []

        # Montagem do registro
        dados.append('E')  # Identificador da linha para Exclusão
        dados.append('D')  # Código da UORG - A(100)
        dados.append(FIM_LINHA)  # Finalizador de linha

        row = DELIMITADOR.join(dados)

        if fd is not None:
            fd.write(f'{row}\n')
        else:
            return row

    def rodape(self, fd=None, registros=10):
        now = datetime.now()

        dados = []

        # Montagem do registro
        dados.append('T')  # Identificador da linha
        dados.append(now.strftime('%d%m%Y%H%M%S'))  # Data Final
        dados.append(str(registros))  # Quantidade de Registros
        dados.append('FIM')  # Identificador de fim de arquivo
        dados.append(FIM_LINHA)  # Finalizador de linha

        row = DELIMITADOR.join(dados)

        if fd is not None:
            fd.write(f'{row}\n')
        else:
            return row

    def handle(self, *args, **options):
        with open('tmp/uargs.txt', 'w') as fd:
            self.cabecalho(fd=fd)

            setores = Setor.objects.siape().all()
            registros = 0
            for setor in tqdm(setores):
                if setor.uo:
                    self.add_registro(setor=setor, fd=fd)
                    registros += 1

            self.rodape(registros=registros, fd=fd)
