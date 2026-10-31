import zipfile

import tqdm
from django.core.files.storage import default_storage

from djtools.management.commands import BaseCommandPlus
from djtools.storages import get_temp_storage
from edu.models import Aluno
from rh.models import UnidadeOrganizacional


class Command(BaseCommandPlus):
    help = 'Gera o arquivo fotos_alunos_campus.zip no storage para ser baixado pelos terminais de refeitorio'

    def handle(self, *args, **options):
        storage = get_temp_storage()
        storage.file_overwrite = True
        arquivo_dump = '/tmp/fotos_alunos.zip'
        for uo in tqdm.tqdm(UnidadeOrganizacional.locals.all()):
            zip_file = zipfile.ZipFile(arquivo_dump, 'w', zipfile.ZIP_DEFLATED)
            for aluno in Aluno.objects.filter(curso_campus__diretoria__setor__uo=uo).exclude(foto='').exclude(foto__isnull=True):
                try:
                    if not aluno.foto:
                        continue
                except Exception:
                    continue
                try:
                    remote_filename = aluno.foto.name.replace('fotos/', 'fotos/150x200/')
                    with default_storage.open(remote_filename) as f:
                        data = f.read()
                    zip_file.writestr(f'{aluno.matricula}.jpg', data)
                except FileNotFoundError:
                    pass
            zip_file.close()
            storage.save(f'fotos/fotos_alunos_{uo.sigla}.zip', open(arquivo_dump, 'rb'))
