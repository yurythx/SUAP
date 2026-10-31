import re

from django import utils
from django.core import exceptions
from django.db import models

import djtools.forms.fields as formfields
from djtools.choices import STATE_CHOICES


class CharFieldPlus(models.CharField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('max_length', 255)
        self.extra_attrs = kwargs.pop('extra_attrs', {})
        self.widget_attrs = kwargs.pop('widget_attrs', {})
        if 'width' in kwargs:
            self.widget_attrs['style'] = 'width: {}px;'.format(kwargs.pop('width'))
        if 'validate_caracter' in kwargs:
            self.validate_caracter = kwargs.pop('validate_caracter')
        else:
            self.validate_caracter = False
        super().__init__(*args, **kwargs)

    def formfield(self, *args, **kwargs):
        field = super().formfield(*args, **kwargs)
        field.widget.attrs.update(self.widget_attrs)
        return field

    def clean(self, value, model_instance):
        value = super().clean(value, model_instance)
        if self.validate_caracter:
            pattern = '^[!-ÿ]{1}[ -ÿ]{0,}[!-ÿ]{1}|[!-ÿ]{1}$'
            occurrences = re.findall(pattern, value)
            if len(occurrences) != 1:
                raise exceptions.ValidationError('Este campo possui caracteres inválidos.')
        return value


class BrSexoField(models.CharField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('max_length', 1)
        kwargs.setdefault('choices', (('M', 'Masculino'), ('F', 'Feminino')))
        super().__init__(*args, **kwargs)


class BrDiaDaSemanaField(models.CharField):
    def __init__(self, *args, **kwargs):
        choices = [(str(utils.dates.WEEKDAYS[i]), str(utils.dates.WEEKDAYS[i])) for i in range(7)]
        kwargs.setdefault('max_length', 50)
        kwargs.setdefault('choices', choices)
        super().__init__(*args, **kwargs)


class BrCpfField(models.CharField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('max_length', 14)
        kwargs.setdefault('verbose_name', 'CPF')
        super().__init__(*args, **kwargs)

    def formfield(self, **kwargs):
        kwargs.setdefault('form_class', formfields.BrCpfField)
        return super(self.__class__, self).formfield(**kwargs)


class BrCnpjField(models.CharField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('max_length', 18)
        kwargs.setdefault('verbose_name', 'CNPJ')
        super().__init__(*args, **kwargs)

    def formfield(self, **kwargs):
        kwargs.setdefault('form_class', formfields.BrCnpjField)
        return super(self.__class__, self).formfield(**kwargs)


class BrCepField(models.CharField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('max_length', 9)
        super().__init__(*args, **kwargs)

    def formfield(self, **kwargs):
        kwargs.setdefault('form_class', formfields.BrCepField)
        return super(self.__class__, self).formfield(**kwargs)


class BrTelefoneField(models.CharField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('max_length', 15)
        super().__init__(*args, **kwargs)

    def formfield(self, **kwargs):
        kwargs.setdefault('form_class', formfields.BrTelefoneField)
        return super(self.__class__, self).formfield(**kwargs)


class BrEstadoBrasileiroField(models.CharField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('max_length', 2)
        kwargs.setdefault('choices', STATE_CHOICES)
        super().__init__(*args, **kwargs)
