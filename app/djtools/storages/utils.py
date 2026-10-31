import hashlib
import os
import tempfile
import time

from django.conf import settings
from django.core.files.storage import default_storage
from django.utils.crypto import get_random_string

from .s3 import MediaS3Storage, PrivateS3Storage, TemporaryS3Storage, download_temporary_content_s3, upload_temporary_s3
from .storage import FileSystemStoragePlus, PrivateFileSystemStorage, TemporaryFileSystemStorage

__all__ = [
    'assure_path_exists',
    'cache_file',
    'copy_file',
    'download_media_content',
    'download_temporary_content',
    'download_temporary_file',
    'get_overwrite_storage',
    'get_private_storage',
    'get_temp_storage',
    'is_remote_storage',
    'move_file',
    'upload_temporary_file',
]


def is_remote_storage():
    """
    Verifica se o storage atual é remoto (S3).

    Returns:
        bool: True se for S3, False caso contrário
    """
    return settings.STORAGES['default']['BACKEND'] == 'djtools.storages.s3.MediaS3Storage'


def assure_path_exists(dir):
    """
    Garante que um diretório existe, criando-o se necessário.

    Args:
        dir (str): Caminho do diretório a ser verificado/criado
    """
    if not os.path.exists(dir):
        os.makedirs(dir)


def get_private_storage():
    """
    Retorna uma instância do storage privado apropriado.

    Returns:
        Storage: PrivateS3Storage se remoto, PrivateFileSystemStorage se local
    """
    if is_remote_storage():
        return PrivateS3Storage()
    return PrivateFileSystemStorage()


def get_temp_storage():
    """
    Retorna uma instância do storage temporário apropriado.

    Returns:
        Storage: TemporaryS3Storage se remoto, TemporaryFileSystemStorage se local
    """
    if is_remote_storage():
        return TemporaryS3Storage()
    return TemporaryFileSystemStorage()


def get_overwrite_storage():
    """
    Retorna uma instância de storage com sobrescrita habilitada.

    Returns:
        Storage: MediaS3Storage ou FileSystemStoragePlus com file_overwrite=True
    """
    if is_remote_storage():
        storage = MediaS3Storage()
    else:
        storage = FileSystemStoragePlus()
    storage.file_overwrite = True
    return storage


def cache_file(remote_filename: str, remote_storage=default_storage):
    """Baixa e armazena em cache um arquivo do armazenamento remoto para o sistema de arquivos local.

    Esta função tenta baixar um arquivo do armazenamento remoto e salvá-lo em um diretório
    local temporário, com lógica de retentativa com recuo exponencial em caso de falhas.

    Args:
        remote_filename (str): O nome/caminho do arquivo no armazenamento remoto para download
        remote_storage (Storage, optional): Instância de armazenamento Django para download.
            O padrão é default_storage.

    Returns:
        str|None: Caminho completo do sistema de arquivos local para o arquivo em cache se
            bem-sucedido, None se o arquivo remoto não existir ou o download falhar após todas
            as tentativas.

    Raises:
        FileNotFoundError: Se o arquivo remoto não puder ser encontrado após as retentativas
        Outras exceções relacionadas ao armazenamento podem ser lançadas dependendo do backend

    Exemplo:
        >>> local_path = cache_file('caminho/para/arquivo/remoto.pdf')
        >>> if local_path:
        >>> # Use o arquivo em cache local
        >>>     with open(local_path, 'rb') as f:
        >>>         conteudo = f.read()
    """
    if remote_filename:
        full_path = os.path.join(settings.TEMP_DIR, f'cache{get_random_string(12)}')
        temp_storage = TemporaryFileSystemStorage(location=full_path)
        attempts = 0
        while attempts < 10:
            try:
                with remote_storage.open(remote_filename, 'rb') as remote_file:
                    cleaned_name = temp_storage.save(remote_filename, remote_file)
                    full_local_filename = os.path.join(full_path, cleaned_name)
                    return full_local_filename
            except FileNotFoundError:
                attempts += 1
                time.sleep(1)
    return None


def download_media_content(relative_remote_path):
    """
    Faz o download do conteúdo de um arquivo de mídia do storage padrão.

    Args:
        relative_remote_path (str): Caminho relativo do arquivo no storage.

    Returns:
        bytes|None: Conteúdo do arquivo em bytes se encontrado, None se o arquivo não existir.

    Raises:
        FileNotFoundError: Se o arquivo não for encontrado no storage.
    """
    try:
        with default_storage.open(relative_remote_path, 'rb') as f:
            content = f.read()
        return content
    except FileNotFoundError:
        return None


def upload_temporary_file(file_path):
    """
    Faz upload de um arquivo temporário para o storage apropriado.

    Args:
        file_path (str): Caminho do arquivo temporário

    Returns:
        str: Caminho do arquivo no storage destino
    """
    if is_remote_storage():
        return upload_temporary_s3(file_path)
    return file_path


def download_temporary_file(file_path):
    """
    Baixa um arquivo temporário do storage.

    Args:
        file_path (str): Caminho do arquivo no storage

    Returns:
        str: Caminho local do arquivo temporário baixado
    """
    if is_remote_storage():
        ext = file_path.split('.')[-1] if '.' in file_path else None
        suffix = f'.{ext}' if ext else None
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        content = download_temporary_content_s3(file_path)
        tmp.write(content)
        return tmp.name
    return file_path


def download_temporary_content(file_path):
    """
    Baixa o conteúdo de um arquivo temporário.

    Args:
        file_path (str): Caminho do arquivo no storage

    Returns:
        bytes: Conteúdo do arquivo em bytes
    """
    if is_remote_storage():
        return download_temporary_content_s3(file_path)
    with open(file_path, 'rb') as f:
        content = f.read()
    return content


def copy_file(original_relative_path, new_relative_path):
    """
    Copia um arquivo dentro do storage.

    Args:
        original_relative_path (str): Caminho relativo do arquivo origem
        new_relative_path (str): Caminho relativo do arquivo destino
    """
    default_storage.save(new_relative_path, default_storage.open(original_relative_path))


def move_file(original_relative_path, new_relative_path):
    """
    Move um arquivo dentro do storage.

    Args:
        original_relative_path (str): Caminho relativo do arquivo origem
        new_relative_path (str): Caminho relativo do arquivo destino
    """
    copy_file(original_relative_path, new_relative_path)
    default_storage.delete(original_relative_path)


def generate_filename(parts: list, file_obj):
    """
    Gera um nome de arquivo único usando um hash SHA-256 de partes de contexto
    e a extensão original do arquivo.

    Args:
        unique_context_parts (list): Uma lista de valores (e.g., IDs, datas)
                                     para formar a base do hash único.
        file_obj: O objeto de arquivo (e.g., Django File object) com um
                  atributo 'name'.

    Returns:
        str: O nome de arquivo único gerado, incluindo a extensão original.
    """
    hash_base = ''.join(str(part) for part in parts)
    filename_hash = hashlib.sha256(hash_base.encode()).hexdigest()

    extension = ''
    if '.' in file_obj.name:
        extension = file_obj.name[file_obj.name.rfind('.') :]

    return filename_hash + extension
