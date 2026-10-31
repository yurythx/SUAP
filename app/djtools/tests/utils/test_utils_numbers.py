from decimal import Decimal

from djtools.utils.masks import mask_money
from djtools.utils.numbers import (
    dExtenso,
    dinheiro_extenso,
    int_to_roman,
    nota_to_float,
    roman_to_int,
    somar_indice,
    somar_qtd,
    str_money_to_decimal,
    text_to_int,
)
import pytest


class StrMoneyToDecimalTest:
    def test_brazilian_format(self):
        assert str_money_to_decimal('1.010,10') == Decimal('1010.10')

    def test_simple_value(self):
        assert str_money_to_decimal('100,00') == Decimal('100.00')

    def test_with_spaces(self):
        assert str_money_to_decimal('1.000,00') == Decimal('1000.00')

    def test_no_cents(self):
        assert str_money_to_decimal('1.000') == Decimal('1000.00')


class IntToRomanTest:
    def test_basic(self):
        assert int_to_roman(1) == 'I'

    def test_4(self):
        assert int_to_roman(4) == 'IV'

    def test_9(self):
        assert int_to_roman(9) == 'IX'

    def test_42(self):
        assert int_to_roman(42) == 'XLII'

    def test_1990(self):
        assert int_to_roman(1990) == 'MCMXC'

    def test_2024(self):
        assert int_to_roman(2024) == 'MMXXIV'

    def test_3999(self):
        assert int_to_roman(3999) == 'MMMCMXCIX'

    def test_raises_value_error_for_0(self):
        with pytest.raises(ValueError):
            int_to_roman(0)

    def test_raises_value_error_for_4000(self):
        with pytest.raises(ValueError):
            int_to_roman(4000)

    def test_raises_value_error_for_negative(self):
        with pytest.raises(ValueError):
            int_to_roman(-1)

    def test_raises_value_error_for_string(self):
        with pytest.raises(ValueError):
            int_to_roman('abc')


class RomanToIntTest:
    def test_basic(self):
        assert roman_to_int('I') == 1

    def test_iv(self):
        assert roman_to_int('IV') == 4

    def test_mcmxc(self):
        assert roman_to_int('MCMXC') == 1990

    def test_lowercase(self):
        assert roman_to_int('xlii') == 42

    def test_raises_type_error_for_non_string(self):
        with pytest.raises(TypeError):
            roman_to_int(42)

    def test_raises_value_error_for_invalid(self):
        with pytest.raises(ValueError):
            roman_to_int('ABC')

    def test_roundtrip(self):
        for n in [1, 5, 10, 50, 100, 500, 1000, 1987, 2024, 3999]:
            assert roman_to_int(int_to_roman(n)) == n


class NotaToFloatTest:
    def test_nota_decimal_disabled(self, settings):
        settings.NOTA_DECIMAL = False
        assert nota_to_float(85) == 85.0

    def test_nota_decimal_enabled(self, settings):
        settings.NOTA_DECIMAL = True
        settings.CASA_DECIMAL = 1
        assert nota_to_float(85) == 8.5


class TextToIntTest:
    def test_digit_string(self):
        assert text_to_int('123') == 123

    def test_none_returns_none(self):
        assert text_to_int(None) is None

    def test_mixed_string(self):
        result = text_to_int('A232')
        assert result == 65505150


class DinheiroExtensoTest:
    def test_zero_reais(self):
        assert dinheiro_extenso('000', '00') == 'zero reais e zero centavos'

    def test_um_real(self):
        assert dinheiro_extenso('001', '00') == 'um real e zero centavos'

    def test_um_centavo(self):
        assert dinheiro_extenso('000', '01') == 'zero reais e um centavo'

    def test_dez_reais(self):
        assert dinheiro_extenso('010', '00') == 'dez reais e zero centavos'


class SomarQtdTest:
    def test_sums_index(self):
        data = [['a', '100,00'], ['b', '200,00']]
        assert somar_qtd(data, 1) == 300

    def test_empty_list(self):
        assert somar_qtd([], 0) == 0

    def test_with_none_values(self):
        data = [['a', None], ['b', '200,00']]
        assert somar_qtd(data, 1) == 200


class SomarIndiceTest:
    def test_sums_index(self):
        data = [['a', '100,00'], ['b', '200,00']]
        assert somar_indice(data, 1) == Decimal('300.00')

    def test_empty_list(self):
        assert somar_indice([], 0) == Decimal('0.0')

    def test_with_none_values(self):
        data = [['a', None], ['b', '200,00']]
        assert somar_indice(data, 1) == Decimal('200.00')

    def test_soma_valores_mascarados_em_notacao_cientifica(self):
        # regressão do balancete de elemento de despesa: os totais vêm do banco como
        # Decimal('0E-11') (qtd com 5 casas x valor com 6 casas) e são mascarados antes de somados
        data = [['a', mask_money(Decimal('0E-11'))], ['b', mask_money(Decimal('200.00'))]]
        assert somar_indice(data, 1) == Decimal('200.00')


class DExtensoTest:
    def setup_method(self):
        self.d = dExtenso()

    def test_cem(self):
        assert self.d.getExtenso('100') == 'cem'

    def test_um(self):
        assert self.d.getExtenso('1') == 'um'

    def test_vinte_e_um(self):
        assert self.d.getExtenso('21') == 'vinte e um'

    def test_cento_e_vinte_e_tres(self):
        assert self.d.getExtenso('123') == 'cento e vinte e três'

    def test_mil(self):
        assert self.d.getExtenso('1000') == 'um mil'

    def test_mil_novecentos_e_oitenta_e_sete(self):
        assert self.d.getExtenso('1987') == 'um mil, novecentos e oitenta e sete'

    def test_dois_mil_e_vinte_e_quatro(self):
        assert self.d.getExtenso('2024') == 'dois mil e vinte e quatro'

    def test_zero_returns_empty(self):
        assert self.d.getExtenso('0') == ''

    def test_escrever_trio_cem(self):
        assert self.d.escrever_trio_extenso('100') == 'cem'

    def test_escrever_trio_zero(self):
        assert self.d.escrever_trio_extenso('000') == 'zero'

    def test_escrever_trio_normal(self):
        assert self.d.escrever_trio_extenso('123') == 'cento e vinte e três'
