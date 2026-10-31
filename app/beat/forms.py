import json

from django.utils.translation import gettext_lazy as _
from django_celery_beat.admin import TaskChoiceField
from django_celery_beat.models import PeriodicTask

from djtools import forms


class AgendamentoForm(forms.ModelFormPlus):
    regtask = TaskChoiceField(
        label=_('Task (registered)'),
        required=True,
    )

    class Meta:
        """Form metadata."""

        model = PeriodicTask
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance:
            self.fields['regtask'].initial = self.instance.task

    def clean(self):
        data = super().clean()
        if data.get('expire_seconds') is not None and data.get('expires'):
            raise forms.ValidationError(_('Only one can be set, in expires and expire_seconds'))
        return data

    def _clean_json(self, field):
        value = self.cleaned_data[field]
        try:
            json.loads(value)
        except ValueError as exc:
            raise forms.ValidationError(
                _('Unable to parse JSON: %s') % exc,
            )
        return value

    def clean_args(self):
        return self._clean_json('args')

    def clean_kwargs(self):
        return self._clean_json('kwargs')

    def save(self, *args, **kwargs):
        self.instance.task = self.cleaned_data['regtask']
        self.instance.queue = 'beat'
        return super().save(*args, **kwargs)
