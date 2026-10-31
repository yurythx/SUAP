from django.contrib.postgres.fields import ArrayField
from django.db import models

import djtools.forms.fields as formfields


class TagsFieldPlus(ArrayField):
    def __init__(self, base_field=None, size=None, **kwargs):
        if not base_field:
            base_field = models.TextField()
        super().__init__(base_field, size, **kwargs)

    def formfield(self, **kwargs):
        kwargs.setdefault('form_class', formfields.TagsFieldPlus)
        return super(self.__class__, self).formfield(**kwargs)
