import logging
import os
import uuid
from io import BufferedWriter, FileIO

from django.conf import settings
from django.core.files.storage import default_storage

from .utils import assure_path_exists

logger = logging.getLogger(__name__)

__all__ = ['AWSUploadBackend', 'AbstractUploadBackend', 'LocalUploadBackend']


class AbstractUploadBackend:
    BUFFER_SIZE = 64 * 2**10

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def setup(self, filename, *args, **kwargs):
        """Responsible for doing any pre-processing needed before the upload
        starts."""

    def update_filename(self, request, filename, *args, **kwargs):
        """Returns a new name for the file being uploaded."""

    def upload_chunk(self, chunk, *args, **kwargs):
        """Called when a string was read from the client, responsible for
        writing that string to the destination file."""
        raise NotImplementedError

    def upload_complete(self, request, filename, *args, **kwargs):
        """Overriden to performs any actions needed post-upload, and returns
        a dict to be added to the render / json context"""

    def upload(self, uploaded, content_length: int, raw_data: bool, *args, **kwargs) -> bool:
        bytes_written = 0
        try:
            if raw_data:
                # File was uploaded via ajax, and is streaming in.
                chunk = uploaded.read(self.BUFFER_SIZE)
                while len(chunk) > 0:
                    bytes_written += len(chunk)
                    self.upload_chunk(chunk, *args, **kwargs)
                    chunk = uploaded.read(self.BUFFER_SIZE)
            else:
                # File was uploaded via a POST, and is here.
                # CONTENT_LENGTH do multipart inclui delimitadores e outros campos: compara com o tamanho do arquivo.
                content_length = uploaded.size
                for chunk in uploaded.chunks():
                    bytes_written += len(chunk)
                    self.upload_chunk(chunk, *args, **kwargs)
        except Exception as e:
            # things went badly.
            logger.error(f'Upload: things went badly: {e}.')
            self._descartar()
            return False
        #
        if content_length == bytes_written:
            return True
        # The upload was canceled by user
        # so delete it
        self._descartar()
        return False

    def _descartar(self) -> None:
        """Descarta o que o upload gravou antes de falhar (exceção ou envio cancelado). Sem efeito por padrão."""

    def assure_unique_filename(self, filename):
        """
        Returns a new name for the file being uploaded.
        Ensure file with name doesn't exist, and if it does,
        create a unique filename to avoid overwriting
        """
        extension = os.path.splitext(filename)[1]
        unique_filename = str(uuid.uuid4())
        return unique_filename + (extension or '')


class LocalUploadBackend(AbstractUploadBackend):
    def setup(self, relative_upload_path, filename, overwriter=False):
        self._absolute_path = os.path.join(settings.MEDIA_ROOT, relative_upload_path)
        assure_path_exists(self._absolute_path)
        if not overwriter:
            filename = self._filepath = self.assure_unique_filename(filename)
        #
        self._filepath = os.path.join(self._absolute_path, filename)
        self._dest = BufferedWriter(FileIO(self._filepath, 'w'))

    def upload_chunk(self, chunk, *args, **kwargs):
        self._dest.write(chunk)

    def _descartar(self) -> None:
        """Fecha o destino e remove o arquivo parcial do disco."""
        if hasattr(self, '_dest'):
            self._dest.close()
        if hasattr(self, '_filepath') and os.path.exists(self._filepath):
            os.remove(self._filepath)

    def upload_complete(self, *args, **kwargs):
        self._dest.close()
        # Note: a relative path to the settings.MEDIA_ROOT
        # is returned by this function
        relative_path = os.path.relpath(self._filepath, settings.MEDIA_ROOT)
        return relative_path


class AWSUploadBackend(AbstractUploadBackend):
    def setup(self, relative_upload_path, filename, overwriter=False):
        self.full_path = f'{relative_upload_path}/{filename}'

    def upload(self, uploaded, content_length: int, raw_data: bool, *args, **kwargs) -> bool:
        bytes_written = 0
        import io

        bytes_io = io.BytesIO()
        try:
            if raw_data:
                # File was uploaded via ajax, and is streaming in.
                chunk = uploaded.read(self.BUFFER_SIZE)
                while len(chunk) > 0:
                    bytes_written += len(chunk)
                    bytes_io.write(chunk)
                    chunk = uploaded.read(self.BUFFER_SIZE)
            else:
                # File was uploaded via a POST, and is here.
                # CONTENT_LENGTH do multipart inclui delimitadores e outros campos: compara com o tamanho do arquivo.
                content_length = uploaded.size
                for chunk in uploaded.chunks():
                    bytes_written += len(chunk)
                    bytes_io.write(chunk)
        except Exception as e:
            # things went badly.
            logger.error(f'AWSUploadBackend: things went badly: {e}.')
            return False

        if content_length == bytes_written:
            self.final_filename = default_storage.save(self.full_path, bytes_io)
            return True
        return False

    def upload_complete(self, *args, **kwargs):
        return getattr(self, 'final_filename', None)
