import os
import pathlib

from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.core.files.storage import FileSystemStorage
from django.core.files.utils import validate_file_name
from django.utils.encoding import filepath_to_uri

__all__ = ['FileSystemStoragePlus', 'PrivateFileSystemStorage', 'TemporaryFileSystemStorage']


class FileSystemStoragePlus(FileSystemStorage):
    file_overwrite = False

    def get_available_overwrite_name(self, name, max_length):
        if max_length is None or len(name) <= max_length:
            return name

        # Adapted from Django
        dir_name, file_name = os.path.split(name)
        file_root, file_ext = os.path.splitext(file_name)
        truncation = len(name) - max_length

        file_root = file_root[:-truncation]
        if not file_root:
            raise SuspiciousFileOperation(
                f'Storage tried to truncate away entire filename "{name}". '
                'Please make sure that the corresponding file field '
                'allows sufficient "max_length".'
            )
        name = os.path.join(dir_name, f'{file_root}{file_ext}')
        return name

    def get_available_name(self, name, max_length=None):
        dir_name, file_name = os.path.split(name)
        if '..' in pathlib.PurePath(dir_name).parts:
            raise SuspiciousFileOperation(f"Detected path traversal attempt in '{dir_name}'")
        validate_file_name(file_name)
        if self.file_overwrite:
            name = self.get_available_overwrite_name(name, max_length)
            if self.exists(name):
                os.remove(os.path.join(self.location, name))
            return name
        return super().get_available_name(name, max_length)

    def url(self, name):
        url = filepath_to_uri(name)
        return self.base_url + url


class PrivateFileSystemStorage(FileSystemStoragePlus):
    def __init__(self, *args, **kwargs):
        kwargs.update(location=settings.MEDIA_PRIVATE)
        kwargs.update(base_url=settings.TEMP_URL)
        super().__init__(*args, **kwargs)


class TemporaryFileSystemStorage(FileSystemStoragePlus):
    def __init__(self, *args, **kwargs):
        if 'location' not in kwargs:
            kwargs.update(location=settings.TEMP_DIR)
        kwargs.update(base_url=settings.TEMP_URL)
        super().__init__(*args, **kwargs)
