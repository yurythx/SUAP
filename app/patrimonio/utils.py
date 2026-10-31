from django import forms
from django.core.validators import EMPTY_VALUES


def mask_numeropa(value):
    """
    '1234123456' -> '1234PA123456'
    """
    value = str(value)
    return value[:4] + 'PA' + value[4:]


class NumeroPAWidget(forms.TextInput):
    def __init__(self, attrs=None):
        if not attrs:
            attrs = {}
        attrs.update({'class': 'numeropa-widget', 'size': '14', 'maxlength': '12'})
        super(self.__class__, self).__init__(attrs=attrs)

    def render(self, name, value, attrs=None, renderer=None):
        if value and len(value) == 10:
            value = mask_numeropa(value)
        return super(self.__class__, self).render(name, value, attrs=attrs)


class NumeroPAField(forms.CharField):
    widget = NumeroPAWidget

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('label', 'Número PA')
        super(self.__class__, self).__init__(*args, **kwargs)
        self.help_text = kwargs.get('help_text', 'Formato: "9999PA123456"')

    default_error_messages = {'invalid': 'O número da PA deve estar no formato 9999PA123456'}

    def clean(self, value):
        value = super().clean(value)
        if value in EMPTY_VALUES:
            return ''
        if len(value) == 10:  # formato "9999123456"
            value = mask_numeropa(value)
        if len(value) != 12:  # formato "9999PA123456"
            raise forms.ValidationError(self.error_messages['invalid'])
        grupos = value.split('PA')
        if not grupos[0].isdigit():
            raise forms.ValidationError(self.error_messages['invalid'])
        if not grupos[1].isdigit():
            raise forms.ValidationError(self.error_messages['invalid'])
        return grupos[0] + 'PA' + grupos[1]


OPERADOR_PATRIMONIO = ['Operador de Patrimônio', 'Coordenador de Patrimônio', 'Coordenador de Patrimônio Sistêmico']
AUDITOR = ['Auditor']
