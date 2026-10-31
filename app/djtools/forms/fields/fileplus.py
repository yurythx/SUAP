import base64
import os
from typing import Any

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.forms.fields import Field
from django.template.defaultfilters import filesizeformat

from djtools.forms.widgets import (
    AjaxFileUploadWidget,
    ClearableFileInputPlus,
    Image,
    PhotoCaptureInput,
)


class FileFieldPlus(forms.FileField):
    """
    Same as FileField, but you can specify:
        * filetypes - list containing allowed content_types. Example: ['pdf', 'png', 'jpg']
        * max_file_size - a number indicating the maximum file size allowed for upload.
            2.5 MB - 2621440
            5   MB - 5242880
            10  MB - 10485760
            20  MB - 20971520
            50  MB - 52428800
            100 MB - 104857600
            250 MB - 262144000
            500 MB - 524288000
    """

    default_error_messages = {
        'max_length': 'Certifique-se de que o nome do arquivo não ultrapasse %(max)d caracteres. O nome atual possui %(length)d caracteres.',
    }

    widget = ClearableFileInputPlus

    def __init__(self, *args, **kwargs):
        self.label = kwargs.get('label')
        self.filetypes = kwargs.pop('filetypes', None)
        self.check_mimetype = kwargs.pop('check_mimetype', True)
        self.max_file_size = kwargs.pop('max_file_size', None)
        self.widget_custom_cls = kwargs.pop('widget_custom_cls', ClearableFileInputPlus)
        if not self.max_file_size:
            self.max_file_size = settings.DEFAULT_FILE_UPLOAD_MAX_SIZE
        super().__init__(*args, **kwargs)
        self.widget = self.widget_custom_cls()
        self.widget.max_file_size = self.max_file_size
        self.widget.extensions = self.get_extensions()
        self.widget.mimetypes = self.get_mimetypes()

    def get_extensions(self):
        if self.filetypes:
            ext_whitelist = []
            if 'pdf' in self.filetypes:
                ext_whitelist += [
                    '.pdf',
                ]
            if 'jpg' in self.filetypes:
                ext_whitelist += ['.jpeg', '.jpg']
            if 'png' in self.filetypes:
                ext_whitelist += [
                    '.png',
                ]
            if 'xls' in self.filetypes:
                ext_whitelist += [
                    '.xls',
                ]
            if 'xlsx' in self.filetypes:
                ext_whitelist += ['.xlsx']
            if 'doc' in self.filetypes:
                ext_whitelist += [
                    '.doc',
                ]
            if 'docx' in self.filetypes:
                ext_whitelist += [
                    '.docx',
                ]
            if 'csv' in self.filetypes:
                ext_whitelist += [
                    '.csv',
                ]
            if 'txt' in self.filetypes:
                ext_whitelist += [
                    '.txt',
                ]
            if 'mov' in self.filetypes:
                ext_whitelist += [
                    '.mov',
                ]
            if 'mp4' in self.filetypes:
                ext_whitelist += [
                    '.mp4',
                ]
            if 'm4a' in self.filetypes:
                ext_whitelist += [
                    '.m4a',
                ]
            return ext_whitelist

    def get_mimetypes(self):
        if self.filetypes:
            mime_whitelist = []
            if 'pdf' in self.filetypes:
                mime_whitelist += [
                    'application/pdf',
                ]
            if 'jpg' in self.filetypes:
                mime_whitelist += ['image/jpeg', 'image/pjpeg']
            if 'png' in self.filetypes:
                mime_whitelist += [
                    'image/png',
                ]
            if 'xls' in self.filetypes:
                mime_whitelist += [
                    'application/vnd.ms-excel',
                    'application/msexcel',
                    'application/x-msexcel',
                    'application/x-ms-excel',
                    'application/x-excel',
                    'application/xls',
                    'application/x-dos_ms_excel',
                    'application/x-xls',
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    'application/ms-excel',
                ]
            if 'xlsx' in self.filetypes:
                mime_whitelist += [
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                ]
            if 'doc' in self.filetypes or 'docx' in self.filetypes:
                mime_whitelist += [
                    'application/msword',
                    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    'application/zip',
                    'multipart/x-zip',
                ]
            if 'csv' in self.filetypes:
                mime_whitelist += ['text/csv', 'text/plain', 'application/vnd.ms-excel']

            if 'txt' in self.filetypes:
                mime_whitelist += [
                    'text/plain',
                ]
            return mime_whitelist

    def __setattr__(self, key: str, value: Any) -> None:
        super().__setattr__(key, value)
        widget = self.__dict__.get('widget')
        if widget is None:
            return
        if key == 'required':
            widget.is_required = value
        if key == 'max_file_size':
            widget.max_file_size = value
        if key == 'filetypes':
            widget.extensions = self.get_extensions()
            widget.mimetypes = self.get_mimetypes()

    def clean(self, *args, **kwargs):
        value = super().clean(*args, **kwargs)
        if value:
            if self.filetypes:
                mime_whitelist = self.get_mimetypes()
                ext_whitelist = self.get_extensions()
                filename = value.name
                try:
                    import magic

                    try:
                        value.seek(0)
                        mime_type = magic.from_buffer(value.read(), mime=True)
                    except magic.MagicException:
                        raise forms.ValidationError('Problemas ao obter o formato do arquivo')
                except ModuleNotFoundError:
                    mime_type = value.content_type
                ext = os.path.splitext(filename)[1].lower()
                if ext not in ext_whitelist or (self.check_mimetype and mime_type not in mime_whitelist):
                    raise forms.ValidationError(
                        'O formato do arquivo não é válido. Por favor, envie um arquivo nos formatos: {}.'.format(', '.join(ext_whitelist))
                    )
                value.seek(0)
            if self.max_file_size:
                try:
                    if hasattr(value, 'size') and value.size > int(self.max_file_size):
                        raise forms.ValidationError(
                            f'Por favor mantenha o arquivo com tamanho até {filesizeformat(self.max_file_size)}. Tamanho atual: {filesizeformat(value.size)}.'
                        )
                except Exception:
                    raise ValidationError('Arquivo inválido por favor substitua-o e tente novamente.')
        return value


class PrivateFileField(FileFieldPlus):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from djtools.storages import get_private_storage

        self.storage = get_private_storage()


class MultiFileField(forms.FileField):
    widget = ClearableFileInputPlus

    default_error_messages = {
        'min_num': 'O número mínimo de arquivos deve ser de: %(min_num)s \
            (%(num_files)s arquivos foram submetidos).',
        'max_num': 'O SUAP aceita o upload de no máximo  %(max_num)s arquivos\
            por vez (%(num_files)s arquivos foram submetidos).',
        'file_size': 'O arquivo: %(uploaded_file_name)s,\
            excede o tamanho máxima de submissão.',
    }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.filetypes = kwargs.pop('filetypes', None)
        self.check_mimetype = kwargs.pop('check_mimetype', True)
        self.min_num = kwargs.pop('min_num', 0)
        self.max_num = kwargs.pop('max_num', None)
        self.max_file_size = kwargs.pop('max_file_size', None)
        if not self.max_file_size:
            self.max_file_size = settings.DEFAULT_FILE_UPLOAD_MAX_SIZE
        super().__init__(*args, **kwargs)
        self.widget.max_file_size = self.max_file_size
        self.widget.multiple = True
        self.widget.extensions = self.get_extensions()
        self.widget.mimetypes = self.get_mimetypes()

    def get_extensions(self):
        if self.filetypes:
            ext_whitelist = []
            if 'pdf' in self.filetypes:
                ext_whitelist += [
                    '.pdf',
                ]
            if 'jpg' in self.filetypes:
                ext_whitelist += ['.jpeg', '.jpg']
            if 'png' in self.filetypes:
                ext_whitelist += [
                    '.png',
                ]
            if 'xls' in self.filetypes:
                ext_whitelist += ['.xls', '.xlsx']
            if 'doc' in self.filetypes:
                ext_whitelist += ['.doc', '.docx']
            if 'csv' in self.filetypes:
                ext_whitelist += [
                    '.csv',
                ]
            return ext_whitelist

    def get_mimetypes(self):
        if self.filetypes:
            mime_whitelist = []
            if 'pdf' in self.filetypes:
                mime_whitelist += [
                    'application/pdf',
                ]
            if 'jpg' in self.filetypes:
                mime_whitelist += ['image/jpeg', 'image/pjpeg']
            if 'png' in self.filetypes:
                mime_whitelist += [
                    'image/png',
                ]
            if 'xls' in self.filetypes:
                mime_whitelist += [
                    'application/vnd.ms-excel',
                    'application/msexcel',
                    'application/x-msexcel',
                    'application/x-ms-excel',
                    'application/x-excel',
                    'application/xls',
                    'application/x-dos_ms_excel',
                    'application/x-xls',
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    'application/ms-excel',
                ]
            if 'doc' in self.filetypes:
                mime_whitelist += ['application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'application/zip', 'multipart/x-zip']
            if 'csv' in self.filetypes:
                mime_whitelist += ['text/csv', 'text/plain', 'application/vnd.ms-excel']
            return mime_whitelist

    def to_python(self, data):
        ret = []
        for item in data:
            ret.append(super().to_python(item))
        return ret

    def validate(self, data):
        super().validate(data)
        num_files = len(data)

        if len(data) and not data[0]:
            num_files = 0
        if num_files < self.min_num:
            raise ValidationError(self.error_messages['min_num'] % {'min_num': self.min_num, 'num_files': num_files})

        elif self.max_num and num_files > self.max_num:
            raise ValidationError(self.error_messages['max_num'] % {'max_num': self.max_num, 'num_files': num_files})
        if num_files:
            for uploaded_file in data:
                if uploaded_file.size > self.max_file_size:
                    raise ValidationError(self.error_messages['file_size'] % {'uploaded_file_name': uploaded_file.name})

    def compress(self, value):
        if value:
            return value
        return None

    def clean(self, *args, **kwargs):
        values = super().clean(*args, **kwargs)
        if values:
            for value in values:
                if self.filetypes:
                    mime_whitelist = self.get_mimetypes()
                    ext_whitelist = self.get_extensions()
                    filename = value.name
                    try:
                        import magic

                        try:
                            mime_type = magic.from_buffer(value.read(1024), mime=True)
                        except magic.MagicException:
                            raise forms.ValidationError('Problemas ao obter o formato do arquivo')
                    except ModuleNotFoundError:
                        mime_type = value.content_type
                    ext = os.path.splitext(filename)[1].lower()
                    if ext not in ext_whitelist or (self.check_mimetype and mime_type not in mime_whitelist):
                        raise forms.ValidationError(
                            'O formato do arquivo não é válido. Por favor, envie um arquivo nos formatos: {}.'.format(', '.join(ext_whitelist))
                        )
                    value.seek(0)
                if self.max_file_size:
                    try:
                        if hasattr(value, 'size') and value.size > int(self.max_file_size):
                            raise forms.ValidationError(
                                f'Por favor mantenha o arquivo com tamanho até {filesizeformat(self.max_file_size)}. Tamanho atual: {filesizeformat(value.size)}.'
                            )
                    except Exception:
                        raise ValidationError('Arquivo inválido por favor substitua-o e tente novamente.')
        return values


class ImageFieldPlus(forms.ImageField):
    widget = ClearableFileInputPlus

    def __init__(self, upload_to='', storage=None, *args, **kwargs):
        self.init = kwargs.pop('initial', None)
        self.max_file_size = kwargs.pop('max_file_size', None)
        if not self.max_file_size:
            self.max_file_size = settings.DEFAULT_FILE_UPLOAD_MAX_SIZE
        self.upload_to = upload_to
        self.storage = storage or default_storage
        super().__init__(*args, **kwargs)
        self.widget = ClearableFileInputPlus()
        self.widget.max_file_size = self.max_file_size
        self.widget.extensions = self.get_extensions()
        self.widget.mimetypes = self.get_mimetypes()
        self.widget.max_file_size = self.max_file_size

    def get_extensions(self):
        return [
            '.jpeg',
            '.jpg',
            '.png',
        ]

    def get_mimetypes(self):
        return [
            'image/jpeg',
            'image/pjpeg',
            'image/png',
        ]

    def clean(self, data, initial=None):
        data = super().clean(data, initial)
        if self.max_file_size and data:
            try:
                if data.size > int(self.max_file_size):
                    raise forms.ValidationError(
                        f'Por favor mantenha o arquivo com tamanho até {filesizeformat(self.max_file_size)}. Tamanho atual: {filesizeformat(data.size)}.'
                    )
            except AttributeError:
                raise ValidationError('Arquivo inválido por favor tente novamente.')
        return data


class AjaxFileUploadField(Field):
    widget = AjaxFileUploadWidget

    def __init__(self, url, onCompleteUploadFunction, *args, multiple=True, sizeLimit=1024 * 1024 * 50, allowedExtensions=None, **kwargs):
        if allowedExtensions is None:
            allowedExtensions = ['pdf']
        super().__init__(*args, **kwargs)
        self.label = ''
        self.widget.url = url
        self.widget.onCompleteUploadFunction = onCompleteUploadFunction
        self.widget.multiple = multiple
        self.widget.sizeLimit = sizeLimit
        self.widget.allowedExtensions = allowedExtensions


class PhotoCaptureField(Field):
    widget = PhotoCaptureInput

    def to_python(self, value):
        if value:
            return base64.b64decode(value.split(',')[1])
        else:
            return None


class ImageViewField(Field):
    widget = Image

    def __init__(self, url_image, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.widget.url_image = url_image
        self.widget.label = kwargs.get('label')
        self.required = False
