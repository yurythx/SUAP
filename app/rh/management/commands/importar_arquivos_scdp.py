import logging
import os
from decimal import Decimal

import pandas as pd
from django.apps import apps
from django.conf import settings

from comum.models import PrestadorServico, Vinculo
from comum.types import PessoaFisicaCadastro, PrestadorServicoCadastro
from djtools.management.commands import BaseCommandPlus
from djtools.utils import mask_cpf
from rh.models import BilheteViagem, PessoaFisica, Servidor, Viagem
from rh.utils import extrai_matricula

Log = apps.get_model('comum', 'log')

log = logging.getLogger(__name__)


class Command(BaseCommandPlus):
    help = 'Inicia a importação das Viagens SCDP'
    path = os.path.join(settings.BASE_DIR, 'rh/arquivos_scdp/')
    path_viagens = os.path.join(path, 'viagens/')
    path_bilhetes = os.path.join(path, 'bilhetes/')

    def handle(self, *args, **options):
        for arquivo in os.listdir(self.path_viagens):
            if arquivo.endswith(('.xls', '.xlsx')):
                log.info('>>> Processando Importar Viagens SCDP...')
                viagens = importar_viagens_scdp(os.path.join(self.path_viagens, arquivo))
                Log.objects.create(
                    titulo='Importação de viagens do SCDP',
                    texto='Foram importados {} Novas Viagens e {} foram Atualizados'.format(viagens['NOVOS'], viagens['ATUALIZADOS']),
                    app='SCDP',
                )
                log.info('>>> Processado(s) {} Novas viagens do SCDP e {} foram Atualizados'.format(viagens['NOVOS'], viagens['ATUALIZADOS']))

        arquivos = [i for i in os.listdir(self.path_viagens) if i.endswith(('.xls', '.xlsx'))]
        for f in arquivos:
            os.remove(self.path_viagens + f)

        for arquivo in os.listdir(self.path_bilhetes):
            if arquivo.endswith(('.xls', '.xlsx')):
                log.info('>>> Processando Importar Bilhetes das Viagens SCDP...')
                bilhetes = importar_bilhetes_viagens_scdp(os.path.join(self.path_bilhetes, arquivo), self.stderr)
                Log.objects.create(
                    titulo='Importação de Bilhetes das viagens do SCDP',
                    texto='Foram importados {} Novas Viagens e {} foram Atualizados'.format(bilhetes['NOVOS'], bilhetes['ATUALIZADOS']),
                    app='SCDP',
                )
                log.info(
                    '>>> Processado(s) {} Novos Bilhetes das viagens do SCDP e {} foram Atualizados'.format(
                        bilhetes['NOVOS'], bilhetes['ATUALIZADOS']
                    )
                )

        arquivos = [i for i in os.listdir(self.path_bilhetes) if i.endswith(('.xls', '.xlsx'))]
        for f in arquivos:
            os.remove(self.path_bilhetes + f)


def importar_viagens_scdp(filepath):
    retorno = {'NOVOS': 0, 'ATUALIZADOS': 0}
    df = pd.read_excel(filepath, header=None)
    for _index, row in df.iloc[1:].iterrows():
        numero_pcdp = row.iloc[2]
        kwargs = {
            'nome_siorg': row.iloc[1],
            'tipo_proposto': row.iloc[6],
            'motivo_viagem': row.iloc[7],
            'objetivo_viagem': row.iloc[8],
            'data_inicio_viagem': pd.to_datetime(row.iloc[9]).date(),
            'data_fim_viagem': pd.to_datetime(row.iloc[10]).date(),
            'situacao': int(row.iloc[11]),
            'quantidade_viagens': int(row.iloc[12]),
            'quantidade_de_dias_afastamento': int(row.iloc[13]),
            'quantidade_de_diarias': Decimal(f'{row.iloc[14]:.2f}'),
            'valor_desconto_auxilio_alimentacao': Decimal(f'{row.iloc[15]:.2f}'),
            'valor_desconto_auxilio_transporte': Decimal(f'{row.iloc[16]:.2f}'),
            'valor_passagem': Decimal(f'{row.iloc[17]:.2f}'),
            'valor_diaria': Decimal(f'{row.iloc[18]:.2f}'),
            'valor_viagem': Decimal(f'{row.iloc[19]:.2f}'),
            'codigo_siorg': (f'{row.iloc[0]:.2f}').rstrip('0').rstrip('.'),
            'nome_proposto': row.iloc[3],
        }
        try:
            if type(row.iloc[5]) is float:
                matricula = extrai_matricula((f'{row.iloc[5]:.2f}').rstrip('0').rstrip('.'))
            else:
                matricula = extrai_matricula(row.iloc[5])
        except Exception:
            matricula = None
        try:
            cpf = mask_cpf(row.iloc[4])
        except Exception:
            cpf = None
        nome_pessoa_fisica = row.iloc[3]
        servidor = None
        vinculo = None

        if cpf:
            if matricula and Servidor.objects.filter(matricula=matricula).exists():
                servidor = Servidor.objects.filter(matricula=matricula)[0]
                vinculo = servidor.get_vinculo()
            elif PessoaFisica.objects.filter(cpf=cpf).exists():
                pessoa_fisica = PessoaFisica.objects.filter(cpf=cpf).first()
                vinculo = Vinculo.objects.filter(pessoa__pessoafisica=pessoa_fisica).order_by('tipo_relacionamento').first()
            else:
                pessoa_fisica: PessoaFisicaCadastro = {
                    'cpf': str(cpf),
                    'nome_registro': nome_pessoa_fisica,
                }
                dados: PrestadorServicoCadastro = {'pessoa_fisica': pessoa_fisica, 'ativo': False}
                prestador = PrestadorServico.update_or_create(dados)['prestador']
                vinculo = prestador.get_vinculo()

        kwargs['servidor'] = servidor
        kwargs['vinculo'] = vinculo

        if Viagem.objects.filter(numero_pcdp=numero_pcdp).exists():
            Viagem.objects.filter(numero_pcdp=numero_pcdp).update(**kwargs)
            retorno['ATUALIZADOS'] = retorno['ATUALIZADOS'] + 1
        else:
            kwargs['numero_pcdp'] = numero_pcdp
            Viagem.objects.create(**kwargs)
            retorno['NOVOS'] = retorno['NOVOS'] + 1

    return retorno


def importar_bilhetes_viagens_scdp(filepath, stderr=None):
    retorno = {'NOVOS': 0, 'ATUALIZADOS': 0, 'ERROS': 0}
    df = pd.read_excel(filepath, header=None)
    for _index, row in df.iloc[1:].iterrows():
        numero_pcdp = row.iloc[0]
        numero = row.iloc[1]
        if isinstance(numero, float) and numero.is_integer():
            numero = str(int(numero))
        kwargs = {'tipo': row.iloc[2], 'status': row.iloc[3]}
        if row.iloc[4]:
            try:
                kwargs['data_emissao'] = pd.to_datetime(row.iloc[4]).date()
            except Exception:
                stderr.write('Não tem data emissão')

        if Viagem.objects.filter(numero_pcdp=numero_pcdp).exists():
            viagem = Viagem.objects.filter(numero_pcdp=numero_pcdp)[0]
            if BilheteViagem.objects.filter(viagem=viagem, numero=numero).exists():
                BilheteViagem.objects.filter(viagem=viagem, numero=numero).update(**kwargs)
                retorno['ATUALIZADOS'] = retorno['ATUALIZADOS'] + 1
            else:
                kwargs['viagem'] = viagem
                kwargs['numero'] = numero
                BilheteViagem.objects.create(**kwargs)
                retorno['NOVOS'] = retorno['NOVOS'] + 1
        else:
            retorno['ERROS'] = retorno['ERROS'] + 1

    return retorno
