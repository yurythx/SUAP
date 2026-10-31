from decimal import Decimal

import pytest
from django import forms

from djtools.forms.fields.number import DecimalFieldPlus, NotaField, DecimalFieldAlmoxPlus, IntegerFieldPlus


@pytest.fixture
def decimal_field():
    return DecimalFieldPlus()


def test_decimalfieldplus_label_parameter():
    field = DecimalFieldPlus(label='Valor')
    assert field.label == 'Valor'


def test_decimalfieldplus_default_label(decimal_field):
    assert decimal_field.label == ''


def test_decimalfieldplus_clean_with_valid_brazilian_format(decimal_field):
    result = decimal_field.clean('1.234,56')
    assert result == Decimal('1234.56')


@pytest.mark.parametrize('value', ['', None])
def test_decimalfieldplus_clean_empty_not_required(value):
    field = DecimalFieldPlus(required=False)
    assert field.clean(value) is None


def test_decimalfieldplus_widget_attrs_with_decimal_places():
    field = DecimalFieldPlus(decimal_places=2)
    widget = field.widget_attrs(field.widget)
    assert widget.get('data-decimal-places') == 2


def test_decimalfieldplus_widget_attrs_without_decimal_places(decimal_field):
    widget = decimal_field.widget_attrs(decimal_field.widget)
    assert 'data-decimal-places' not in widget


@pytest.mark.parametrize('value', [None, ''])
def test_notafield_clean_returns_none(value):
    field = NotaField()
    assert field.clean(value) is None


def test_notafield_clean_valid_integer_string(settings):
    settings.NOTA_DECIMAL = False
    field = NotaField()
    assert field.clean('85') == 85


def test_notafield_clean_decimal_strips_separators(settings):
    settings.NOTA_DECIMAL = True
    settings.CASA_DECIMAL = 2
    field = NotaField()
    assert field.clean('85') == 85


def test_notafield_clean_integer_value(settings):
    settings.NOTA_DECIMAL = False
    field = NotaField()
    assert field.clean('0') == 0


def test_notafield_clean_negative_value_raises():
    field = NotaField()
    with pytest.raises(forms.ValidationError, match='maior ou igual a 0'):
        field.clean('-1')


def test_notafield_clean_exceeds_max(settings):
    settings.NOTA_DECIMAL = False
    field = NotaField()
    with pytest.raises(forms.ValidationError, match='menor ou igual a 100'):
        field.clean('101')


def test_notafield_clean_decimal_exceeds_max(settings):
    settings.NOTA_DECIMAL = True
    settings.CASA_DECIMAL = 2
    field = NotaField()
    with pytest.raises(forms.ValidationError, match='menor ou igual a 10'):
        field.clean('1001')


def test_notafield_clean_non_numeric_raises():
    field = NotaField()
    with pytest.raises(forms.ValidationError, match='deve ser um número'):
        field.clean('abc')


def test_decimalfieldalmoxplus_help_text_default():
    field = DecimalFieldAlmoxPlus()
    assert field.help_text == 'Formato: "9.999,999999"'


def test_decimalfieldalmoxplus_clean_valid():
    field = DecimalFieldAlmoxPlus()
    result = field.clean('1.234,567')
    assert result == Decimal('1234.567')


def test_decimalfieldalmoxplus_clean_seis_casas_decimais():
    field = DecimalFieldAlmoxPlus()
    assert field.clean('1.234,123456') == Decimal('1234.123456')


def test_decimalfieldalmoxplus_widget_formata_valor_com_seis_casas():
    field = DecimalFieldAlmoxPlus()
    assert field.widget.format_value(Decimal('1234.5')) == '1.234,500000'


def test_decimalfieldalmoxplus_widget_mantem_valor_ja_formatado():
    field = DecimalFieldAlmoxPlus()
    assert field.widget.format_value('1.234,123456') == '1.234,123456'


def test_decimalfieldalmoxplus_edicao_preserva_valor():
    """O valor renderizado na edição deve voltar íntegro pelo clean (sem inflar/truncar)."""
    field = DecimalFieldAlmoxPlus()
    valor = Decimal('1234.123456')
    assert field.clean(field.widget.format_value(valor)) == valor


def test_decimalfieldalmoxplus_clean_empty_not_required():
    field = DecimalFieldAlmoxPlus(required=False)
    assert field.clean('') is None


def test_integerfieldplus_default_max_length():
    field = IntegerFieldPlus()
    assert field.max_length == 255


def test_integerfieldplus_clean_valid_int():
    field = IntegerFieldPlus()
    assert field.clean('42') == 42


def test_integerfieldplus_clean_empty_not_required():
    field = IntegerFieldPlus(required=False)
    assert field.clean('') is None


def test_integerfieldplus_clean_non_numeric_raises():
    field = IntegerFieldPlus()
    with pytest.raises(forms.ValidationError, match='apenas com números'):
        field.clean('abc')


def test_integerfieldplus_widget_attrs_width():
    field = IntegerFieldPlus(width=200)
    assert field._widget_attrs == {'style': 'width: 200px;'}
