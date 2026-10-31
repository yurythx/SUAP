from django.db import models

from djtools.forms import widgets


class BooleanFieldPlus(models.BooleanField):
    def formfield(self, **kwargs):
        field = super(self.__class__, self).formfield(**kwargs)
        if type(field.widget) is widgets.CheckboxInput:
            field.widget = widgets.RadioSelect()
            field.widget.choices = [(True, 'Sim'), (False, 'Não')]
        else:
            field.widget.choices = [(None, 'Não Informado'), (True, 'Sim'), (False, 'Não')]

        return field
