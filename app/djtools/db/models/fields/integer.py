from django.db import models

import djtools.forms.fields as formfields


class NotaField(models.PositiveIntegerField):
    def formfield(self, **kwargs):
        kwargs.setdefault('form_class', formfields.NotaField)
        field = super().formfield(**kwargs)
        field.widget = formfields.NotaField.widget()
        return field


class IntegerFieldPlus(models.IntegerField):
    def __init__(self, *args, **kwargs):
        self.extra_attrs = kwargs.pop('extra_attrs', {})
        super().__init__(*args, **kwargs)


class PositiveIntegerFieldPlus(models.PositiveIntegerField):
    """permite informar um valor mínimo diferente de zero através do
    parâmetro 'min_value'
    """

    def __init__(self, *args, **kwargs):
        self.min_value = kwargs.pop('min_value', 0)
        if self.min_value < 0:
            self.min_value = 0
        #
        super().__init__(*args, **kwargs)

    def formfield(self, **kwargs):
        defaults = {'min_value': self.min_value}
        defaults.update(kwargs)
        return super().formfield(**defaults)
