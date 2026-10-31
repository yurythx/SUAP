import json
import os
import re

import jsonschema
from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import EMPTY_VALUES, validate_email
from django.utils.translation import gettext_lazy as _

from djtools.forms.widgets import (
    AlphaNumericUpperCaseWidget,
    AlphaNumericWidget,
    CapitalizeTextWidget,
    JSONEditorWidget,
    ProcessoEletronicoWidget,
)


class CharFieldPlus(forms.CharField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('max_length', 255)
        self._widget_attrs = kwargs.pop('widget_attrs', {})
        if 'width' in kwargs:
            self._widget_attrs['style'] = 'width: {}px;'.format(kwargs.pop('width'))
        if 'validate_caracter' in kwargs:
            self.validate_caracter = kwargs.pop('validate_caracter')
        else:
            self.validate_caracter = False
        super().__init__(*args, **kwargs)

    def widget_attrs(self, widget):
        attrs = super().widget_attrs(widget)
        attrs.update(self._widget_attrs)
        return attrs

    def clean(self, value):
        value = super().clean(value)
        if self.validate_caracter:
            pattern = '^[!-ÿ]{1}[ -ÿ]{0,}[!-ÿ]{1}|[!-ÿ]{1}$'
            occurrences = re.findall(pattern, value)
            if len(occurrences) != 1:
                raise forms.ValidationError('Este campo possui caracteres inválidos.')
        return value


class ProcessoEletronicoField(forms.CharField):
    default_error_messages = {
        'invalid': _('Favor, informar um número de Processo Eletrônico válido.'),
        'max_digits': _('Este campo requer um valor de 17 dígitos.'),
        'digits_only': _('Favor, preencher somente com números.'),
    }

    widget = ProcessoEletronicoWidget

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('label', 'Número do processo')
        super().__init__(*args, **kwargs)
        self.help_text = kwargs.get('help_text', 'Formato: "12345.123456' + settings.NUM_PROCESSO_DIVISOR_SUFIXO + '2024-12"')

    def clean(self, value):
        value = super().clean(value)
        if value in EMPTY_VALUES:
            return ''
        if not re.match(r'\d\d\d\d\d.\d\d\d\d\d\d' + settings.NUM_PROCESSO_DIVISOR_SUFIXO + r'\d\d\d\d-\d\d', value):
            raise forms.ValidationError(self.error_messages['invalid'])
        orig_value = value[:]
        if not value.isdigit():
            value = re.sub(r'[-\.\\' + settings.NUM_PROCESSO_DIVISOR_SUFIXO + ']', '', value)
        try:
            int(value)
        except ValueError:
            raise forms.ValidationError(self.error_messages['digits_only'])
        if len(value) != 17:
            raise forms.ValidationError(self.error_messages['max_digits'])

        return orig_value


class AlphaNumericField(forms.CharField):
    widget = AlphaNumericWidget

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    default_error_messages = {'invalid': 'O campo pode ser preenchido apenas com números ou letras'}


class AlphaNumericUpperCaseField(forms.CharField):
    widget = AlphaNumericUpperCaseWidget

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    default_error_messages = {'invalid': 'O campo pode ser preenchido apenas com números ou letras maiúsculas'}


class CapitalizeTextField(forms.CharField):
    widget = CapitalizeTextWidget

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    default_error_messages = {'invalid': 'O campo pode ser preenchido apenas com números ou letras'}


class JSONSchemaField(CharFieldPlus):
    def __init__(self, schema, options, ajax=True, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.schemadir = getattr(settings, 'JSONFORMS_SCHEMA_DIR', settings.STATIC_ROOT)
        self.backvalidate = getattr(settings, 'JSONFORMS_SCHEMA_VALIDATE', True)

        self.schema = self.load(schema)

        if ajax:
            self.widget = JSONEditorWidget(schema=schema, options=options)
        else:
            self.options = self.load(options)
            self.widget = JSONEditorWidget(schema=self.schema, options=self.options)

    def load(self, value):
        if isinstance(value, dict):
            return value
        elif isinstance(value, str):
            file_path = os.path.join(self.schemadir, value)
            if os.path.isfile(file_path):
                static_file = open(file_path)
                json_value = json.loads(static_file.read())
                static_file.close()
                return json_value

            return None

    def to_python(self, value):
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                raise ValidationError('Invalid JSON')
        return value

    def clean(self, value):
        value = super().clean(value)

        if self.backvalidate:
            try:
                jsonschema.validate(value, self.schema)
            except jsonschema.exceptions.ValidationError as e:
                raise ValidationError(message=e.message)

        return value

    def prepare_value(self, value):
        if isinstance(value, dict | list):
            return json.dumps(value)
        return value


class MultiEmailField(forms.CharField):
    widget = forms.Textarea

    def to_python(self, value):
        return value.replace(' ', '')

    def validate(self, value):
        value = value.replace(' ', '')
        super().validate(value)
        if value:
            for email in value.split(','):
                validate_email(email)
