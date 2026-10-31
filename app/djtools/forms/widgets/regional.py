from decimal import Decimal

from django.conf import settings
from django.forms import TextInput

from djtools.utils import (
    mask_cnpj,
    mask_cpf,
    mask_money,
    mask_money_almox,
    mask_nota,
    mask_placa,
    mask_processo_eletronico,
)


class MoneyWidgetMixin:
    def render(self, name, value, attrs=None, renderer=None):
        value = self.format_value(value)
        return super().render(name, value, attrs=attrs)


class BrTelefoneWidget(TextInput):
    def __init__(self, attrs=None):
        if attrs is None:
            attrs = {}
        attrs.update({'class': 'br-phone-number-widget', 'size': '18', 'maxlength': '18'})
        super().__init__(attrs=attrs)


class ProcessoEletronicoWidget(TextInput):
    def __init__(self, attrs=None):
        if attrs is None:
            attrs = {}
        attrs.update({'class': 'br-processoeletronico-widget', 'size': '17', 'maxlength': '17', 'minlength': '17'})
        super(self.__class__, self).__init__(attrs=attrs)

    def render(self, name, value, attrs=None, renderer=None):
        if value and value.isdigit() and len(value) == 17:
            value = mask_processo_eletronico(value)
        return super(self.__class__, self).render(name, value, attrs=attrs)


class BRCpfCnpjWidget(TextInput):
    def __init__(self, attrs=None):
        if attrs is None:
            attrs = {}
        attrs.update({'class': 'br-cpf-cnpj-widget', 'size': '18', 'maxlength': '18'})
        super(self.__class__, self).__init__(attrs=attrs)

    def render(self, name, value, attrs=None, renderer=None):
        return super(self.__class__, self).render(name, value, attrs=attrs)


class BRCpfWidget(TextInput):
    def __init__(self, attrs=None):
        if attrs is None:
            attrs = {}
        attrs.update({'class': 'br-cpf-widget', 'size': '14', 'maxlength': '14'})
        super(self.__class__, self).__init__(attrs=attrs)

    def render(self, name, value, attrs=None, renderer=None):
        if value and value.isdigit() and len(value) == 11:
            value = mask_cpf(value)
        return super(self.__class__, self).render(name, value, attrs=attrs)


class BrCnpjWidget(TextInput):
    def __init__(self, attrs=None):
        if attrs is None:
            attrs = {}
        attrs.update({'class': 'br-cnpj-widget', 'size': '18', 'maxlength': '18'})
        super(self.__class__, self).__init__(attrs=attrs)

    def render(self, name, value, attrs=None, renderer=None):
        if value and value.isdigit() and len(value) == 14:
            value = mask_cnpj(value)
        return super(self.__class__, self).render(name, value, attrs=attrs)


class BrDinheiroWidget(MoneyWidgetMixin, TextInput):
    def __init__(self, attrs=None):
        if attrs is None:
            attrs = {}
        attrs.update({'class': 'br-dinheiro-widget', 'size': '15', 'maxlength': '15'})
        super().__init__(attrs=attrs)

    def format_value(self, value):
        if value is None:
            value = ''
        expected_types = (str, Decimal, int)
        if not isinstance(value, expected_types):
            raise ValueError(f'Value type must be in {expected_types[0]} {expected_types[1]}')

        if isinstance(value, str) and (value == '' or ',' in value):
            # value is blank or already formatted
            return value
        else:
            try:
                return mask_money(value)
            except Exception:  # adicionado para o caso de inserir um valor diferente do padrão, por exemplo a letra acentuada "ã"
                return value


class NotaWidget(TextInput):
    def __init__(self, attrs=None):
        if attrs is None:
            attrs = {}
        length = 3
        if settings.NOTA_DECIMAL:
            attrs.update({'onkeyup': f'mask_nota(this, {settings.CASA_DECIMAL} )'})
            if settings.CASA_DECIMAL == 2:
                length = 4
        attrs.update({'class': 'nota-widget', 'maxlength': length})
        super().__init__(attrs=attrs)

    def render(self, name, value, attrs=None, renderer=None):
        value = mask_nota(value)
        return super().render(name, value, attrs=attrs, renderer=renderer)


class BrDinheiroAlmoxWidget(MoneyWidgetMixin, TextInput):
    # 9 dígitos inteiros + 6 decimais => '999.999.999,999999' (18 caracteres)
    casas_decimais = 6

    def __init__(self, attrs=None):
        if attrs is None:
            attrs = {}
        attrs.update({'class': 'br-dinheiro-almox-widget', 'size': '18', 'maxlength': '18', 'data-decimal-places': str(self.casas_decimais)})
        super().__init__(attrs=attrs)

    def format_value(self, value):
        if value is None or value == '':
            return ''
        if isinstance(value, str) and ',' in value:
            # value is already formatted
            return value
        try:
            return mask_money_almox(value, self.casas_decimais)
        except Exception:  # valor fora do padrão (ex.: texto digitado indevidamente); mantém o que o usuário informou
            return value


class BrPlacaVeicularWidget(TextInput):
    def __init__(self, attrs=None):
        if attrs is None:
            attrs = {}
        attrs.update({'class': 'placa-widget', 'size': '10', 'maxlength': '8'})
        super().__init__(attrs=attrs)

    def render(self, name, value, attrs=None, renderer=None):
        if value and len(value) == 7:
            value = mask_placa(value)
        return super().render(name, value, attrs=attrs)


class BrCepWidget(TextInput):
    class Media:
        js = ('/static/djtools/consulta_cep/js/consulta_cep.js',)

    def __init__(self, attrs=None):
        if attrs is None:
            attrs = {}
        attrs.update({'class': 'br-cep-widget', 'size': '9', 'maxlength': '9'})
        super().__init__(attrs=attrs)
