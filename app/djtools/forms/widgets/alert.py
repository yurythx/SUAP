from django import forms
from django.utils.safestring import mark_safe


class AlertWidget(forms.HiddenInput):
    def __init__(self, info, *args, **kwargs):
        self.info = info
        super().__init__(*args, **kwargs)

    def render(self, name, value, attrs=None, renderer=None):
        html = super().render(name, value, attrs=attrs, renderer=renderer)
        return mark_safe(f'<p class="alert alert-info">{self.info}</p>{html}')
