import logging
import os
import tempfile
import zipfile
from datetime import datetime
from os.path import basename
from zipfile import ZipFile

from django.apps import apps
from django.core.exceptions import SuspiciousFileOperation
from django.core.files.storage import default_storage

from contracheques.migracao import importar_contracheque
from djtools.management.commands import BaseCommandPlus
from djtools.storages import cache_file

log = logging.getLogger(__name__)

Log = apps.get_model('comum', 'log')


class Command(BaseCommandPlus):
    help = 'Inicia a importação Contracheques'
    path = 'tmp/contracheques/arquivos_contracheque/'
    backups_fita_espelho = 'contracheques/backups_fita_espelho/'

    def handle(self, *args, **options):
        _diretorio, arquivos = default_storage.listdir(self.path)
        for arquivo in arquivos:
            eh_test = False
            if arquivo.split('_')[0] == 'test':
                eh_test = True

            tipo = ''
            if arquivo.find('servidores') != -1:
                tipo = 'servidores'
            elif arquivo.find('pensionistas') != -1:
                tipo = 'pensionistas'
            else:
                continue
            log.info(f'>>> Iniciando Importação dos Contracheques dos {tipo}... {arquivo}')
            f = default_storage.open(os.path.join(self.path, arquivo), 'rb')
            contracheques = importar_contracheque(f, tipo)
            log.info(f'>>> Finalizando Importação dos Contracheques dos {tipo}... {arquivo}')

            if not eh_test:
                Log.objects.create(
                    titulo=f'Importação de Fita Espelho {tipo}',
                    texto='Foram importados {} Novos Contracheques e {} foram Atualizados'.format(
                        contracheques['NOVOS'], contracheques['ATUALIZADOS']
                    ),
                    app='CC',
                )
            log.info('>>> Processado(s) {} Novos Contracheques e {} foram Atualizados'.format(contracheques['NOVOS'], contracheques['ATUALIZADOS']))

        arquivos = [i for i in arquivos if i.endswith('.txt')]
        # zipar os arquivos encontrados e salvar na pasta de backups dos contracheques
        if arquivos:
            file_zip_name = f'{self.backups_fita_espelho}fita_espelho_{datetime.now()}.zip'
            temp = tempfile.NamedTemporaryFile(suffix='.zip', mode='w+b', delete=False)
            temp.close()
            zipObj = ZipFile(temp.name, 'w', zipfile.ZIP_DEFLATED)
            check_arquivos = 0
            for f in arquivos:
                if f.split('_')[0] == 'test':
                    continue
                arquivo_path = os.path.join(self.path, f)
                with default_storage.open(arquivo_path, 'rb') as arq:
                    try:
                        local_filename = cache_file(arq.name)
                    except SuspiciousFileOperation:
                        local_filename = os.path.relpath(arq.name)
                    zipObj.write(local_filename, basename(arq.name))
                    try:
                        os.unlink(local_filename)
                    except FileNotFoundError:
                        pass
                check_arquivos += 1

            zipObj.close()
            default_storage.save(file_zip_name, open(temp.name, 'rb'))

            try:
                os.unlink(temp.name)
            except FileNotFoundError:
                pass

            # excluir os arquivos processados da pasta de media
            for f in arquivos:
                arquivo_path = os.path.join(self.path, f)
                default_storage.delete(arquivo_path)
