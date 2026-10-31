"""
Inspirado em http://code.google.com/p/django-thumbs/
Melhorias:
- redimensionamento da imagem
- guarda os thumbs em pastas separadas para cada tamanho
- opção use_id_for_name
"""

import io
import os
import tempfile

from django import forms
from django.core.signing import Signer
from django.db.models import ImageField
from django.db.models.fields.files import ImageFieldFile
from PIL import Image, ImageOps
from djtools.forms.widgets import ClearableFileInputPlus

EXIF_ORIENTATION = 0x0112


class ImageWithThumbsFieldFile(ImageFieldFile):
    """
    See ImageWithThumbsField for usage example
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.field.sizes:
            for size in self.field.sizes:
                setattr(self, 'url_{}x{}'.format(*size), self.get_thumb_url(size))

    @property
    def url(self):
        if not self:
            return ''
        return self.storage.url(self.name)

    def get_url_publica(self, size=None):
        if not self:
            return ''
        model = type(self.instance)
        app_label = model._meta.app_label
        model_name = model._meta.model_name
        pk = getattr(self.instance, 'uuid', self.instance.pk)
        name = self.field.name
        if size:
            return f'/djtools/arquivo/{app_label}/{model_name}/{pk}/{name}/{size}/'
        else:
            return f'/djtools/arquivo/{app_label}/{model_name}/{pk}/{name}/'

    def get_thumb_url(self, size):
        if not self:
            return ''
        splited = list(os.path.split(self.name))
        splited.insert(-1, f'{size[0]}x{size[1]}')
        relative_path = os.path.join(*splited)
        return self.field.storage.url(relative_path)

    def save(self, name, content, save=True):
        extension = name.split('.')[-1]
        if self.field.use_id_for_name:
            string_randomica = Signer(salt='extra-salt').sign(self.instance.id).split(':')[1][:12]
            name = f'{self.instance.id}.{string_randomica}.{extension}'
        super().save(name, content, save)
        if self.field.sizes:
            for size in self.field.sizes:
                thumb_dir = os.path.join(self.field.upload_to, f'{size[0]}x{size[1]}')
                file_name = os.path.join(self.field.upload_to, name)

                with self.field.storage.open(file_name) as f:
                    content = io.BytesIO(f.read())

                imin = Image.open(content)
                code = imin.getexif().get(EXIF_ORIENTATION, 1)

                if code and code != 1:
                    imin = ImageOps.exif_transpose(imin)

                width, height = imin.size
                nwidth = (height // 4) * 3
                x = (width - nwidth) // 2
                if x > 0:
                    imout = imin.crop((x, 0, width - x, height))
                else:
                    imout = imin.crop((0, 0, width, height))
                imout = imout.resize(size)
                thumb_file = os.path.join(thumb_dir, name)
                imout = imout.convert('RGB')
                tmp = tempfile.NamedTemporaryFile(suffix=f'.{extension}')
                imout.save(tmp)
                tmp.seek(0)
                self.field.storage.save(thumb_file, tmp)
                tmp.close()

    def delete(self, save=True):
        name = self.name
        super().delete(save)
        if self.field.sizes:
            for size in self.field.sizes:
                splited = list(os.path.split(name))
                splited.insert(-1, f'{size[0]}x{size[1]}')
                thumb_name = os.path.join(*splited)
                try:
                    self.storage.delete(thumb_name)
                except Exception:
                    pass


class ImageFormFieldWithThumbs(forms.ImageField):
    widget = ClearableFileInputPlus

    def is_compatible(self, binary_data):
        content = io.BytesIO(binary_data)
        imin = Image.open(content)
        code = imin.getexif().get(EXIF_ORIENTATION, 1)

        if code and code != 1:
            imin = ImageOps.exif_transpose(imin)

        width, height = imin.size
        nwidth = (height // 4) * 3
        x = (width - nwidth) // 2
        if x > 0:
            imout = imin.crop((x, 0, width - x, height))
        else:
            imout = imin.crop((0, 0, width, height))
        imout = imout.resize((75, 100))
        imout.convert('RGB')

    def clean(self, data, initial=None):
        super().clean(data, initial)
        try:
            if data:
                content = data.read()
                data.file.seek(0)
                self.is_compatible(content)
        except Exception:
            raise forms.ValidationError('Foto com formato inválido, por favor escolha outra.')
        return data


class ImageWithThumbsField(ImageField):
    attr_class = ImageWithThumbsFieldFile

    def __init__(self, verbose_name=None, name=None, width_field=None, height_field=None, sizes=None, **kwargs):
        self.verbose_name = verbose_name
        self.name = name
        self.width_field = width_field
        self.height_field = height_field
        self.sizes = sizes
        self.use_id_for_name = kwargs.pop('use_id_for_name', True)
        super().__init__(**kwargs)

    def formfield(self, **kwargs):
        return super().formfield(
            **{
                'form_class': ImageFormFieldWithThumbs,
                **kwargs,
            }
        )
