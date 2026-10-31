from django.db import models

import djtools.forms.fields as formfields


class DecimalFieldPlus(models.DecimalField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('decimal_places', 2)
        kwargs.setdefault('max_digits', 12)
        super().__init__(*args, **kwargs)

    def formfield(self, **kwargs):
        kwargs.setdefault('form_class', formfields.DecimalFieldPlus)
        return super(self.__class__, self).formfield(**kwargs)
