import decimal

from django import forms

from djtools.forms.widgets import (
    BrDinheiroWidget,
    DictInputWidget,
)


class DictInputField(forms.CharField):
    def __init__(self, *args, items=None, **kwargs):
        verbose_name = kwargs.get('label')
        widget = kwargs.pop('widget', None)
        initial = kwargs.get('initial')
        kwargs['widget'] = DictInputWidget(items=items or {}, widget=widget, initial=initial, verbose_name=verbose_name)
        kwargs['label'] = ''
        super().__init__(*args, **kwargs)

    def clean(self, value):
        cleaned = {}
        values = value.split('|')
        for i, (k, _v) in enumerate(self.widget.items.items()):
            cleaned[k] = values[i]
            if type(self.widget.widget) is BrDinheiroWidget:
                cleaned[k] = decimal.Decimal(cleaned[k].replace('.', '').replace(',', '.')) if cleaned[k] else None
            if self.required and cleaned[k] in (None, ''):
                self.widget.error_message = f'Informe um valor para o item {i + 1}.'
                raise forms.ValidationError(self.widget.error_message)
        return cleaned
