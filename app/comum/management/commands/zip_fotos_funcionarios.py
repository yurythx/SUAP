import os
import tempfile
import zipfile

import tqdm
from django.core.files.storage import default_storage

from comum.models import PrestadorServico
from djtools.management.commands import BaseCommandPlus
from djtools.storages import get_temp_storage
from rh.models import Servidor


class Command(BaseCommandPlus):
    help = 'Gera o arquivo fotos_funcionarios.zip no storage para ser baixado pelos terminais de ponto'

    def handle(self, *args, **options):
        storage = get_temp_storage()
        storage.file_overwrite = True
        temp = tempfile.NamedTemporaryFile(suffix='.zip', mode='w+b', delete=False)
        temp.close()
        arquivo_dump = temp.name
        zip_file = zipfile.ZipFile(arquivo_dump, 'w', zipfile.ZIP_DEFLATED)
        # foto migrou de PessoaFisica para Vinculo; acessa via AbstractRelacionamento.foto → Vinculo.foto
        for s in tqdm.tqdm(Servidor.objects.ativos().filter(vinculos__foto__isnull=False).exclude(vinculos__foto='')):
            if not s.foto:
                continue
            try:
                remote_filename = s.foto.name.replace('fotos/', 'fotos/150x200/')
                with default_storage.open(remote_filename) as f:
                    data = f.read()
                zip_file.writestr(f'{s.matricula}.jpg', data)
            except FileNotFoundError:
                pass
        for s in tqdm.tqdm(PrestadorServico.objects.filter(ativo=True).filter(vinculos__foto__isnull=False).exclude(vinculos__foto='')):
            if not s.foto:
                continue
            try:
                remote_filename = s.foto.name.replace('fotos/', 'fotos/150x200/')
                with default_storage.open(remote_filename) as f:
                    data = f.read()
                zip_file.writestr(f'{s.matricula}.jpg', data)
            except FileNotFoundError:
                try:
                    remote_filename = s.foto.name.replace('fotos/', 'fotos/75x100/')
                    with default_storage.open(remote_filename) as f:
                        data = f.read()
                    zip_file.writestr(f'{s.matricula}.jpg', data)
                except FileNotFoundError:
                    pass
        zip_file.close()
        storage.save('fotos/fotos_funcionarios.zip', open(arquivo_dump, 'rb'))
        try:
            os.unlink(arquivo_dump)
        except FileNotFoundError:
            pass
