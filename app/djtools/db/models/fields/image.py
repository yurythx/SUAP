import os
import uuid

from django.db import models

import djtools.forms.fields as formfields


class ImageFieldPlus(models.ImageField):
    def __init__(self, verbose_name=None, name=None, width_field=None, height_field=None, **kwargs):
        self.filetype = kwargs.pop('filetypes', None)
        self.check_mimetype = kwargs.pop('check_mimetype', True)
        self.max_file_size = kwargs.pop('max_file_size', None)
        self.width_field, self.height_field = width_field, height_field
        super().__init__(verbose_name, name, **kwargs)

    def formfield(self, **kwargs):
        kwargs.setdefault('form_class', formfields.ImageFieldPlus)
        kwargs.setdefault('max_file_size', self.max_file_size)
        return super().formfield(**kwargs)

    def generate_filename(self, instance, filename):
        filename = super().generate_filename(instance, filename)
        name, ext = os.path.splitext(filename)
        name = name.replace(ext, '').replace('.', '_')
        filename = f'{name}-{uuid.uuid4().hex}{ext}'
        return filename
