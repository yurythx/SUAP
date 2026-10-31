import datetime
import os
import uuid

from django.core import checks, exceptions
from django.db import models

import djtools.forms.fields as formfields
from djtools.storages.utils import get_private_storage, is_remote_storage


class FieldFilePlus(models.fields.files.FieldFile):
    @property
    def url(self):
        if not self:
            return ''
        return self.storage.url(self.name)

    def get_url_publica(self):
        model = type(self.instance)
        app_label = model._meta.app_label
        model_name = model._meta.model_name
        pk = self.instance.pk
        name = self.field.name
        return f'/djtools/arquivo/{app_label}/{model_name}/{pk}/{name}/'


class PrivateFieldFilePlus(FieldFilePlus):
    @property
    def url(self):
        if not self:
            return ''
        if is_remote_storage():
            return self.storage.url(self.name)
        return f'/djtools/private_media/?media={self.name}'


class FileFieldPlus(models.FileField):
    attr_class = FieldFilePlus

    def __init__(self, *args, **kwargs):
        self.filetype = kwargs.pop('filetypes', None)
        self.check_mimetype = kwargs.pop('check_mimetype', True)
        self.max_file_size = kwargs.pop('max_file_size', None)
        self.can_view = kwargs.pop('can_view', None)
        self.create_date_subdirectories = kwargs.pop('create_date_subdirectories', False)
        self.force_filename = kwargs.pop('force_filename', None)
        super().__init__(*args, **kwargs)

    def _check_upload_to(self):
        if not self.upload_to:
            return [
                checks.Error(
                    f"O 'upload_to' de {self.__class__.__name__} é um campo obrigatório.",
                    obj=self,
                    id='fields.E202',
                    hint='Adicione o atributo no FileFieldPlus.',
                )
            ]
        return super()._check_upload_to()

    def formfield(self, **kwargs):
        kwargs.setdefault('form_class', formfields.FileFieldPlus)
        kwargs.setdefault('filetypes', self.filetype)
        kwargs.setdefault('check_mimetype', self.check_mimetype)
        kwargs.setdefault('max_file_size', self.max_file_size)
        return super().formfield(**kwargs)

    def validate(self, value, model_instance):
        super().validate(value, model_instance)
        try:
            self.storage.generate_filename(value)
        except Exception:
            raise exceptions.ValidationError('O nome do arquivo não é válido. Verifique se o nome contém caracteres especiais ou espaços.')

    def generate_filename(self, instance, filename):
        filename = super().generate_filename(instance, filename)
        if self.create_date_subdirectories:
            directory = os.path.dirname(filename)
            name = os.path.basename(filename)
            today = datetime.datetime.today().strftime('%Y/%m/%d')
            directory = f'{directory}/{today}'
            filename = f'{directory}/{name}'
        name, ext = os.path.splitext(filename)
        name = name.replace(ext, '').replace('.', '_')
        filename = f'{name}-{uuid.uuid4().hex}{ext}'
        return filename

    @staticmethod
    def original_filename(file_field):
        """Não é exatamente o nome original, o que seria ideal pela
        perspectiva do usuário. O nome original é tratado e convertido
        para um determinado padrão (ver FileFieldPlus.generate_filename).

        Então, este método retorna apenas o nome do arquivo sem
        o sufixo inserido no método FileFieldPlus.generate_filename.
        """
        file_name_with_ext = os.path.basename(file_field.name)
        file_name, ext = os.path.splitext(file_name_with_ext)
        file_name_parts = file_name.split('-')
        file_name_no_sufix_parts = file_name_parts[:-1]
        if file_name_no_sufix_parts:
            file_name_final_parts = file_name_no_sufix_parts
        else:
            file_name_final_parts = file_name_parts
        original_filename = f'{"-".join(file_name_final_parts)}{ext}'
        return original_filename


class PrivateFileField(FileFieldPlus):
    attr_class = PrivateFieldFilePlus

    def __init__(self, *args, **kwargs):
        kwargs.update(storage=get_private_storage())
        super().__init__(*args, **kwargs)

    def formfield(self, **kwargs):
        kwargs.setdefault('form_class', formfields.PrivateFileField)
        return super().formfield(**kwargs)
