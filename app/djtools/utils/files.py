import logging
import os
import string

import magic
from django.apps import apps
from django.conf import settings
from django.db import models

from djtools.storages import download_media_content

logger = logging.getLogger(__name__)


def get_file_information(relative_path: str, file_name=None) -> dict:
    file_name = file_name or os.path.basename(relative_path)
    file_type = '?'
    file_type_mime = '?'
    file_type_mime_display = '?'
    file_size_bytes = 0
    file_size_kbytes = 0
    file_size_mbytes = 0
    file_size_display = '?'

    try:
        file_content = download_media_content(relative_path)
        file_type = magic.from_buffer(file_content)
        file_type_mime = magic.from_buffer(file_content, mime=True)
        file_type_mime_display = get_file_type_mime_display(file_type_mime)
        file_size_bytes = len(file_content)
        file_size_kbytes = round(file_size_bytes / 1024)
        file_size_mbytes = round(file_size_kbytes / 1024)
        file_size_display = ''
        if file_size_bytes >= 1024:
            if file_size_kbytes >= 1024:
                # em MB
                file_size_display += f' {file_size_mbytes:,} MB'.replace('.', '_').replace(',', '.').replace('_', '.')
            else:
                # em KB
                file_size_display += f' {file_size_kbytes:,} KB'.replace('.', '_').replace(',', '.').replace('_', '.')
            file_size_display += f' ({file_size_bytes:,} bytes)'.replace('.', '_').replace(',', '.').replace('_', '.')
        else:
            # em Bytes
            file_size_display += f'{file_size_bytes:,} bytes'.replace('.', '_').replace(',', '.').replace('_', '.')
    except Exception:
        pass

    return {
        'file_name': file_name,
        'file_type': file_type,
        'file_type_mime': file_type_mime,
        'file_type_mime_display': file_type_mime_display,
        'file_size_bytes': file_size_bytes,
        'file_size_kbytes': file_size_kbytes,
        'file_size_mbytes': file_size_mbytes,
        'file_size_display': file_size_display,
    }


def get_file_type_mime_display(file_type_mime: str) -> str:
    """https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/MIME_types/Common_types"""

    if file_type_mime == 'application/octet-stream':
        return 'Arquivo Desconhecido'

    if file_type_mime == 'text/plain':
        return 'Arquivo Texto'

    if file_type_mime == 'image/vnd.microsoft.icon':
        return 'Arquivo Ícone'

    if file_type_mime == 'application/msword':
        return 'Documento DOC'

    if file_type_mime == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
        return 'Documento DOCX'

    if file_type_mime == 'application/vnd.oasis.opendocument.text':
        return 'Documento ODT'

    if file_type_mime == 'application/vnd.ms-powerpoint':
        return 'Apresentação PPT'

    if file_type_mime == 'application/vnd.openxmlformats-officedocument.presentationml.presentation':
        return 'Apresentação PPTX'

    if file_type_mime == 'application/vnd.ms-excel':
        return 'Planilha XLS'

    if file_type_mime == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':
        return 'Planilha XLSX'

    if 'text/' in file_type_mime:
        return f'Arquivo {file_type_mime.split("/")[1].upper()}'

    if 'image/' in file_type_mime:
        return f'Imagem {file_type_mime.split("/")[1].upper()}'

    if 'audio/' in file_type_mime:
        return f'Áudio {file_type_mime.split("/")[1].upper()}'

    if 'video/' in file_type_mime:
        return f'Vídeo {file_type_mime.split("/")[1].upper()}'

    if 'font/' in file_type_mime:
        return f'Fonte {file_type_mime.split("/")[1].upper()}'

    if 'application/' in file_type_mime:
        return f'Documento {file_type_mime.split("/")[1].upper()}'

    return file_type_mime


def walk(path):
    """
    Função que navega a partir de uma raiz nos diretórios do sistema opracional.

    Args:
        path (string): contem o diretório base para navegação.

    Returns:
        Lista contendo a raiz, os diretórios e os arquivos.
    """
    for root, dirs, files in os.walk(path, topdown=True):
        dirs[:] = [d for d in dirs if d in settings.INSTALLED_APPS_SUAP]
        yield [root, dirs, files]


def procurar_arquivos_ausentes():
    for model in apps.get_models():
        logger.info(f'Verificando arquivos ausentes para model: {model}')
        for field in [f for f in model._meta.fields if isinstance(f, models.FileField)]:
            values_list = (
                model.objects.exclude(**{field.attname: ''}).exclude(**{field.attname: None}).values_list('id', field.attname).order_by('id')
            )
            for pk, filename in values_list:
                if callable(field.upload_to):
                    part1 = ''
                else:
                    part1 = settings.MEDIA_ROOT
                filename_path = os.path.join(part1, filename)
                if not os.path.exists(filename_path):
                    logger.warning(f'Arquivo ausente - pk: {pk}, field: {field.attname}, path: {filename_path}')


def formata_nome_arquivo(s):
    valid_chars = f'-_.() {string.ascii_letters}{string.digits}'
    filename = ''.join(c for c in s if c in valid_chars)
    filename = filename.replace(' ', '_')
    if filename.startswith('.'):
        return filename[1:]
    return filename


def limitar_tamanho_nome_arquivo(filename, length_limit):
    if len(filename) > length_limit:
        extension = '.{}'.format(filename.split('.')[-1])
        filename = filename[: length_limit - len(extension)]
        filename = f'{filename}{extension}'
    return filename
