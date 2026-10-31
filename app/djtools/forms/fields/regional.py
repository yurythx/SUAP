import re

from django import forms
from django.core.validators import EMPTY_VALUES
from django.utils.encoding import smart_str
from django.utils.translation import gettext_lazy as _

from djtools.choices import STATE_CHOICES
from djtools.forms.widgets import (
    BrCepWidget,
    BrCnpjWidget,
    BRCpfCnpjWidget,
    BRCpfWidget,
    BrPlacaVeicularWidget,
    BrTelefoneWidget,
)
from djtools.utils import cnpj_valido, cpf_valido, mask_cnpj, mask_cpf, mask_placa


def DV_maker(v):
    if v >= 2:
        return 11 - v
    return 0


SEQUENCIA_REPETIDA = 'sequencia_repetida'


def eh_sequencia_repetida(valor: str) -> bool:
    """CPF/CNPJ com todos os dígitos iguais: fecha o cálculo do DV, mas não é documento (#17410)."""
    digitos = re.sub(r'\D', '', valor)
    return len(digitos) > 1 and len(set(digitos)) == 1


class SequenciaRepetidaLegadaMixin:
    """Recusa CPF/CNPJ com dígitos iguais só quando digitado ou alterado no form (#17410).

    O ``clean`` do campo recusa sempre (é o que ``cpf_valido``/``cnpj_valido`` usam). Aqui, no
    ponto do form que conhece o valor inicial, o erro é relevado quando o registro já tinha o
    documento e o usuário não mexeu no campo: há milhares de cadastros legados assim
    (000.000.000-00) que continuariam editáveis. Vale para Form, ModelForm e admin, pois
    ``Form._clean_fields`` sempre passa por ``Field._clean_bound_field`` (hook interno do
    Django 5.x, o mesmo que o ``FileField`` usa para ler o inicial).
    """

    def _clean_bound_field(self, bf: forms.BoundField) -> str:
        try:
            return super()._clean_bound_field(bf)
        except forms.ValidationError as e:
            inicial = str(bf.initial or '')
            if e.code == SEQUENCIA_REPETIDA and re.sub(r'\D', '', inicial) == re.sub(r'\D', '', str(bf.data or '')):
                return inicial
            raise


class BrTelefoneField(forms.Field):
    widget = BrTelefoneWidget

    def __init__(self, *args, **kwargs):
        if 'max_length' in kwargs:
            kwargs.pop('max_length')
        kwargs.pop('empty_value', None)
        super().__init__(*args, **kwargs)
        self.help_text = kwargs.get('help_text', 'Formato: "(99) 99999-9999"')

    default_error_messages = {'invalid': 'O número deve estar no formato (99) 99999-9999.'}

    def clean(self, value):
        super().clean(value)
        if value in EMPTY_VALUES:
            return ''
        value = re.sub(r'(\(|\)|\s+)', '', smart_str(value))
        phone_digits_re = re.compile(r'^(\d{2})[-\.]?(\d{4,5})[-\.]?(\d{4})$')
        m = phone_digits_re.search(value)
        if m:
            return f'({m.group(1)}) {m.group(2)}-{m.group(3)}'
        raise forms.ValidationError(self.error_messages['invalid'])


class BrCepField(forms.RegexField):
    widget = BrCepWidget

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('help_text', 'Formato: "99999-999"')
        kwargs['max_length'] = 9
        super().__init__(r'^\d{5}-\d{3}$', *args, **kwargs)

    def clean(self, value):
        value = super().clean(value)
        if value in EMPTY_VALUES:
            return ''
        if not re.match(r'\d\d\d\d\d-\d\d\d', value):
            raise forms.ValidationError(self.error_messages['invalid'])
        return value


class BrCpfCnpjField(SequenciaRepetidaLegadaMixin, forms.CharField):
    default_error_messages = {
        'invalid': 'CPF/CNPJ inválido.',
        'max_digits': _('This field requires at most 11 digits or 14 characters.'),
        'digits_only': _('This field requires only numbers.'),
    }

    widget = BRCpfCnpjWidget

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('label', 'CPF/CNPJ')
        super().__init__(*args, **kwargs)
        self.help_text = kwargs.get('help_text', '(Informe o número do CPF/CNPJ corretamente e sem ponto ou barra)')

    def clean(self, value: str | None) -> str:
        value = super().clean(value)
        if value in EMPTY_VALUES:
            return ''
        if eh_sequencia_repetida(value):
            raise forms.ValidationError(self.error_messages['invalid'], code=SEQUENCIA_REPETIDA)
        # As regras de DV moram só no BrCpfField/BrCnpjField, via cpf_valido/cnpj_valido.
        if len(value) == 11:  # formato "99999999999" - cpf
            value, valido = mask_cpf(value), cpf_valido
        elif len(value) == 14:  # formato "99999999999999" - cnpj
            value, valido = mask_cnpj(value), cnpj_valido
        else:
            raise forms.ValidationError(self.error_messages['invalid'])
        if not valido(value):
            raise forms.ValidationError(self.error_messages['invalid'])
        return value


class BrCpfField(SequenciaRepetidaLegadaMixin, forms.CharField):
    default_error_messages = {
        'invalid': _('Favor, informar um CPF válido.'),
        'max_digits': _('Este campo requer um valor entre 11 e 14 dígitos.'),
        'digits_only': _('Favor, preencher somente com números.'),
    }

    widget = BRCpfWidget

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('label', 'CPF')
        super().__init__(*args, **kwargs)
        self.help_text = kwargs.get('help_text', 'Formato: "XXX.XXX.XXX-XX"')

    def clean(self, value: str | None) -> str:
        value = super().clean(value)
        if value in EMPTY_VALUES:
            return ''
        if eh_sequencia_repetida(value):
            raise forms.ValidationError(self.error_messages['invalid'], code=SEQUENCIA_REPETIDA)
        if len(value) == 11 and value.isdigit():  # formato "99999999999"
            value = mask_cpf(value)
        if len(value) != 14:  # formato "999.999.999-99"
            raise forms.ValidationError(self.error_messages['invalid'])
        if not re.match(r'\d\d\d.\d\d\d.\d\d\d-\d\d', value):
            raise forms.ValidationError(self.error_messages['invalid'])
        orig_value = value[:]
        if not value.isdigit():
            value = re.sub(r'[-\.]', '', value)
        try:
            int(value)
        except ValueError:
            raise forms.ValidationError(self.error_messages['digits_only'])
        if len(value) != 11:
            raise forms.ValidationError(self.error_messages['max_digits'])
        orig_dv = value[-2:]

        new_1dv = sum(i * int(value[idx]) for idx, i in enumerate(range(10, 1, -1)))
        new_1dv = DV_maker(new_1dv % 11)
        value = value[:-2] + str(new_1dv) + value[-1]
        new_2dv = sum(i * int(value[idx]) for idx, i in enumerate(range(11, 1, -1)))
        new_2dv = DV_maker(new_2dv % 11)
        value = value[:-1] + str(new_2dv)
        if value[-2:] != orig_dv:
            raise forms.ValidationError(self.error_messages['invalid'])

        return orig_value


class BrCnpjField(SequenciaRepetidaLegadaMixin, forms.CharField):
    default_error_messages = {
        'invalid': _('Informe um CNPJ válido.'),
        'digits_only': _('Preencha somente com números.'),
        'max_digits': _('Este campo requer 14 dígitos.'),
    }

    widget = BrCnpjWidget

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('label', 'CNPJ')
        super().__init__(*args, **kwargs)
        self.help_text = kwargs.get('help_text', 'Formato: "XX.XXX.XXX/XXXX-XX"')

    def clean(self, value: str | None) -> str:
        """
        Value can be either a string in the format XX.XXX.XXX/XXXX-XX or a
        group of 14 characters.
        """
        value = super().clean(value)
        if value in EMPTY_VALUES:
            return ''
        if eh_sequencia_repetida(value):
            raise forms.ValidationError(self.error_messages['invalid'], code=SEQUENCIA_REPETIDA)
        if len(value) == 14:  # formato "XXXXXXXXXXXXXX"
            value = mask_cnpj(value)
        if len(value) != 18:  # formato "XX.XXX.XXX/XXXX-XX"
            raise forms.ValidationError(self.error_messages['invalid'])
        if not re.match(r'\d\d.\d\d\d.\d\d\d/\d\d\d\d-\d\d', value):
            raise forms.ValidationError(self.error_messages['invalid'])
        orig_value = value[:]
        if not value.isdigit():
            value = re.sub(r'[-\./]', '', value)
        try:
            int(value)
        except ValueError:
            raise forms.ValidationError(self.error_messages['digits_only'])
        if len(value) != 14:
            raise forms.ValidationError(self.error_messages['max_digits'])
        orig_dv = value[-2:]

        new_1dv = sum(i * int(value[idx]) for idx, i in enumerate(list(range(5, 1, -1)) + list(range(9, 1, -1))))
        new_1dv = DV_maker(new_1dv % 11)
        value = value[:-2] + str(new_1dv) + value[-1]
        new_2dv = sum(i * int(value[idx]) for idx, i in enumerate(list(range(6, 1, -1)) + list(range(9, 1, -1))))
        new_2dv = DV_maker(new_2dv % 11)
        value = value[:-1] + str(new_2dv)
        if value[-2:] != orig_dv:
            raise forms.ValidationError(self.error_messages['invalid'])

        return orig_value


class BrPlacaVeicularField(forms.CharField):
    widget = BrPlacaVeicularWidget

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('label', 'Placa')
        super().__init__(*args, **kwargs)
        self.help_text = kwargs.get('help_text', 'Formato: "AAA-1111 (Padrão Antigo)" ou "AAA-1A11 (Padrão Mercosul)"')

    default_error_messages = {'invalid': 'A placa deve estar no formato AAA-1111 ou AAA-1A11'}

    def clean(self, value):
        value = super().clean(value)
        if value in EMPTY_VALUES:
            return ''
        if len(value) == 7:  # formato "AAA1A11"
            value = mask_placa(value)
        if len(value) != 8:  # formato "AAA-1111"
            raise forms.ValidationError(self.error_messages['invalid'])
        grupos = value.split('-')
        if not grupos[0].isalnum():
            raise forms.ValidationError(self.error_messages['invalid'])
        else:
            letras = grupos[0].upper()
        if not grupos[1].isalnum():
            raise forms.ValidationError(self.error_messages['invalid'])
        return letras + '-' + grupos[1]


class BrEstadoBrasileiroField(forms.ChoiceField):
    def __init__(self, choices=STATE_CHOICES, required=True, widget=None, label=None, initial=None, help_text=None, **kwargs):
        super().__init__(choices=choices, required=required, widget=widget, label=label, initial=initial, help_text=help_text, **kwargs)


class MesField(forms.ChoiceField):
    meses = [
        [1, 'Janeiro'],
        [2, 'Fevereiro'],
        [3, 'Março'],
        [4, 'Abril'],
        [5, 'Maio'],
        [6, 'Junho'],
        [7, 'Julho'],
        [8, 'Agosto'],
        [9, 'Setembro'],
        [10, 'Outubro'],
        [11, 'Novembro'],
        [12, 'Dezembro'],
    ]

    def __init__(self, *args, label=None, empty_label=None, **kwargs):
        super().__init__(*args, label=label, **kwargs)
        # verifica se foi utilizado algum atributo para o rótulo principal (empty_label para os ModelChoiceField)
        if empty_label:
            self.choices = [[0, empty_label], *self.meses]
        else:
            self.choices = self.meses

    def to_python(self, value):
        value = super().to_python(value)
        if value:
            value = int(str(value))
        return value

    def valid_value(self, value):
        choices = self.choices() if callable(self.choices) else self.choices
        return any(value == k for k, v in choices)
