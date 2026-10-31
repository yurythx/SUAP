from django import forms
from django.core.validators import EMPTY_VALUES

from patrimonio.utils import OPERADOR_PATRIMONIO


def mask_empenho(value):
    """
    '1234123456' -> '1234NE123456'
    """
    value = str(value)
    return value[:4] + 'NE' + value[4:]


class NumEmpenhoWidget(forms.TextInput):
    def __init__(self, attrs=None):
        if not attrs:
            attrs = {}
        attrs.update({'class': 'empenho-widget', 'size': '14', 'maxlength': '12'})
        super(self.__class__, self).__init__(attrs=attrs)

    def render(self, name, value, attrs=None, renderer=None):
        if value and len(value) == 10:
            value = mask_empenho(value)
        return super(self.__class__, self).render(name, value, attrs=attrs)


class NumEmpenhoField(forms.CharField):
    widget = NumEmpenhoWidget

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('label', 'Número de empenho')
        super(self.__class__, self).__init__(*args, **kwargs)
        self.help_text = kwargs.get('help_text', 'Formato: "9999NE123456"')

    default_error_messages = {'invalid': 'O número de empenho deve estar no formato 9999NE123456'}

    def clean(self, value):
        value = super().clean(value)
        if value in EMPTY_VALUES:
            return ''
        if len(value) == 10:  # formato "9999123456"
            value = mask_empenho(value)
        if len(value) != 12:  # formato "9999NE123456"
            raise forms.ValidationError(self.error_messages['invalid'])
        grupos = value.split('NE')
        if not grupos[0].isdigit():
            raise forms.ValidationError(self.error_messages['invalid'])
        if not grupos[1].isdigit():
            raise forms.ValidationError(self.error_messages['invalid'])
        return grupos[0] + 'NE' + grupos[1]


OPERADOR_ALMOXARIFADO = ['Operador de Almoxarifado', 'Coordenador de Almoxarifado', 'Coordenador de Almoxarifado Sistêmico']
TODOS_GRUPOS_ALMOXARIFADO = ['Operador de Almoxarifado', 'Coordenador de Almoxarifado', 'Coordenador de Almoxarifado Sistêmico', 'Auditor']
OPERADOR_ALMOXARIFADO_OU_PATRIMONIO = OPERADOR_ALMOXARIFADO + OPERADOR_PATRIMONIO
