from decimal import Decimal
from django.conf import settings
from django import forms

from djtools.forms.widgets import (
    BrDinheiroAlmoxWidget,
    BrDinheiroWidget,
    IntegerWidget,
    NotaWidget,
)


class DecimalFieldPlus(forms.DecimalField):
    widget = BrDinheiroWidget

    def __init__(self, label='', *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.label = label
        self.help_text = kwargs.get('help_text', 'Formato: "9.999,99"')

    def clean(self, value):
        if not self.required and not value:
            return None
        if value:
            value = value.replace('.', '').replace(',', '.')
        try:
            return Decimal(value)
        except Exception:
            raise forms.ValidationError(self.error_messages['invalid'])

    def widget_attrs(self, widget):
        attrs = super().widget_attrs(widget)

        if self.decimal_places:
            attrs.setdefault('data-decimal-places', self.decimal_places)

        return attrs


class NotaField(DecimalFieldPlus):
    widget = NotaWidget

    def clean(self, value):
        if value is None or value == '':
            return None
        if settings.NOTA_DECIMAL and isinstance(value, str):
            value = value.replace('.', '').replace(',', '')
        try:
            value = int(value)
        except ValueError:
            raise forms.ValidationError('A nota deve ser um número.')
        if value < 0:
            raise forms.ValidationError('A nota deve ser maior ou igual a 0 (zero).')
        if value > (1000 if settings.NOTA_DECIMAL and settings.CASA_DECIMAL == 2 else 100):
            nota_max = '10' if settings.NOTA_DECIMAL else '100'
            raise forms.ValidationError(f'A nota deve ser menor ou igual a {nota_max}.')
        return value


class DecimalFieldAlmoxPlus(forms.DecimalField):
    widget = BrDinheiroAlmoxWidget

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.help_text = kwargs.get('help_text', 'Formato: "9.999,999999"')

    def clean(self, value):
        if not self.required and not value:
            return None
        if value:
            value = value.replace('.', '').replace(',', '.')
        try:
            return Decimal(value)
        except Exception:
            raise forms.ValidationError(self.error_messages['invalid'])


class IntegerFieldPlus(forms.CharField):
    widget = IntegerWidget

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('max_length', 255)
        self._widget_attrs = kwargs.pop('widget_attrs', {})
        if 'width' in kwargs:
            self._widget_attrs['style'] = 'width: {}px;'.format(kwargs.pop('width'))
        super().__init__(*args, **kwargs)

    default_error_messages = {'invalid': 'O campo deve ser preenchido apenas com números'}

    def clean(self, value):
        if not self.required and not value:
            return None
        try:
            return int(value)
        except Exception:
            raise forms.ValidationError(self.error_messages['invalid'])
