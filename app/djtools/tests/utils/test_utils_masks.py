from decimal import Decimal

import pytest

from djtools.utils.masks import (
    anonimizar_cpf,
    anonimizar_documento,
    anonimizar_matricula,
    format_telefone,
    mask_cep,
    mask_ch_componente,
    mask_cnpj,
    mask_cpf,
    mask_money,
    mask_money_almox,
    mask_nota,
    mask_number,
    mask_numbers,
    mask_placa,
    mask_processo_eletronico,
    split_thousands,
    decimal_para_str,
)


class SplitThousandsTest:
    def test_short_value(self):
        assert split_thousands('123') == '123'

    def test_with_default_separator(self):
        assert split_thousands('1234567') == '1.234.567'

    def test_with_custom_separator(self):
        assert split_thousands('1234567', sep=',') == '1,234,567'

    def test_negative_value(self):
        assert split_thousands('-1234567') == '-1.234.567'

    def test_integer_input(self):
        assert split_thousands(1234567) == '1.234.567'

    def test_small_negative(self):
        assert split_thousands('-123') == '-123'

    def test_three_digits(self):
        assert split_thousands('999') == '999'

    def test_nao_remove_sinal_interno(self):
        # o sinal do expoente não pode ser confundido com o sinal do valor
        assert not split_thousands('0E-11').startswith('-')


class StrPontoFixoTest:
    def test_zero_em_notacao_cientifica(self):
        # total zerado de qtd (5 casas) x valor (6 casas) volta do banco como 0E-11
        assert decimal_para_str(Decimal('0E-11')) == '0.00000000000'

    def test_zero_negativo_vira_positivo(self):
        assert decimal_para_str(Decimal('-0E-11')) == '0.00000000000'

    def test_expoente_positivo(self):
        assert decimal_para_str(Decimal('1E+3')) == '1000'

    def test_valor_pequeno(self):
        assert decimal_para_str(Decimal('1.23E-9')) == '0.00000000123'

    def test_valor_ja_em_ponto_fixo(self):
        assert decimal_para_str(Decimal('-1234.50')) == '-1234.50'

    def test_inteiro(self):
        assert decimal_para_str(1000) == '1000'

    def test_nao_numerico(self):
        assert decimal_para_str('1.234,56') == '1.234,56'


class MaskNumbersTest:
    def test_extracts_digits(self):
        assert mask_numbers('012abc345def') == '012345'

    def test_empty_string(self):
        assert mask_numbers('') == ''

    def test_only_letters(self):
        assert mask_numbers('abc') == ''

    def test_only_numbers(self):
        assert mask_numbers('12345') == '12345'

    def test_with_special_chars(self):
        assert mask_numbers('(84) 1234-5678') == '8412345678'


class MaskPlacaTest:
    def test_formats_plate(self):
        assert mask_placa('AAA1111') == 'AAA-1111'

    def test_mercosul_plate(self):
        assert mask_placa('BRA1A23') == 'BRA-1A23'


class MaskNumberTest:
    def test_none_returns_none(self):
        assert mask_number(None) is None

    def test_integer_no_decimal(self):
        assert mask_number('42') == '42'

    def test_with_decimal(self):
        assert mask_number('3.14') == '3,14'

    def test_trailing_zero_decimal(self):
        assert mask_number('3.0') == 3

    def test_integer_input(self):
        assert mask_number(42) == '42'


class MaskMoneyTest:
    def test_integer(self):
        assert mask_money(1) == '1,00'

    def test_thousands(self):
        assert mask_money(1000) == '1.000,00'

    def test_with_cents(self):
        assert mask_money(1000.99) == '1.000,99'

    def test_string_input(self):
        assert mask_money('1234.5') == '1.234,5'

    def test_long_cents_truncated(self):
        assert mask_money('1234.567') == '1.234,56'

    def test_zero(self):
        assert mask_money(0) == '0,00'

    def test_zero_em_notacao_cientifica(self):
        # regressão: 0E-11 virava '-0.E11,00' e quebrava o balancete de elemento de despesa
        assert mask_money(Decimal('0E-11')) == '0,00'

    def test_zero_negativo_em_notacao_cientifica(self):
        assert mask_money(Decimal('-0E-11')) == '0,00'

    def test_expoente_positivo(self):
        assert mask_money(Decimal('1E+3')) == '1.000,00'


class MaskMoneyAlmoxTest:
    def test_integer(self):
        assert mask_money_almox(1) == '1,000000'

    def test_thousands(self):
        assert mask_money_almox(1000) == '1.000,000000'

    def test_completa_casas_decimais(self):
        assert mask_money_almox(Decimal('1000.5')) == '1.000,500000'

    def test_mantem_seis_casas_decimais(self):
        assert mask_money_almox(Decimal('1.123456')) == '1,123456'

    def test_trunca_alem_das_casas_decimais(self):
        assert mask_money_almox('1234.1234567') == '1.234,123456'

    def test_casas_decimais_customizadas(self):
        assert mask_money_almox(Decimal('1.5'), casas_decimais=3) == '1,500'

    def test_zero(self):
        assert mask_money_almox(0) == '0,000000'

    def test_negativo(self):
        assert mask_money_almox(Decimal('-1234.5')) == '-1.234,500000'

    def test_zero_em_notacao_cientifica(self):
        assert mask_money_almox(Decimal('0E-11')) == '0,000000'

    def test_valor_pequeno_em_notacao_cientifica(self):
        assert mask_money_almox(Decimal('1.23E-9')) == '0,000000'


class MaskNotaTest:
    def test_nota_decimal_disabled(self, settings):
        settings.NOTA_DECIMAL = False
        assert mask_nota(85) == 85

    def test_nota_decimal_1_place(self, settings):
        settings.NOTA_DECIMAL = True
        settings.CASA_DECIMAL = 1
        assert mask_nota(85) == '8,5'

    def test_nota_decimal_2_places(self, settings):
        settings.NOTA_DECIMAL = True
        settings.CASA_DECIMAL = 2
        assert mask_nota(85) == '0,85'

    def test_nota_decimal_rounding(self, settings):
        settings.NOTA_DECIMAL = True
        settings.CASA_DECIMAL = 1
        assert mask_nota(80) == '8,0'

    def test_nota_decimal_padding(self, settings):
        settings.NOTA_DECIMAL = True
        settings.CASA_DECIMAL = 2
        assert mask_nota(5) == '0,05'

    def test_nota_decimal_large(self, settings):
        settings.NOTA_DECIMAL = True
        settings.CASA_DECIMAL = 2
        assert mask_nota(1000) == '10,00'


class MaskChComponenteTest:
    def test_ch_decimal_enabled(self, settings):
        settings.COMPONENTE_CH_DECIMAL = True
        assert mask_ch_componente(100) == Decimal('1.00')

    def test_ch_decimal_disabled(self, settings):
        settings.COMPONENTE_CH_DECIMAL = False
        assert mask_ch_componente(100) == 100

    def test_ch_decimal_none(self, settings):
        settings.COMPONENTE_CH_DECIMAL = True
        assert mask_ch_componente(None) is None


class MaskCpfTest:
    def test_formats_cpf(self):
        assert mask_cpf('00000000000') == '000.000.000-00'

    def test_already_clean(self):
        assert mask_cpf('00000000000', clean=False) == '000.000.000-00'

    def test_with_dirty_input(self):
        assert mask_cpf('000.000.000-00') == '000.000.000-00'

    def test_empty_string(self):
        assert mask_cpf('') == ''


class MaskProcessoEletronicoTest:
    def test_formats_process(self, settings):
        settings.NUM_PROCESSO_DIVISOR_SUFIXO = '/'
        from django.conf import settings

        result = mask_processo_eletronico('00000000000000000')
        assert result == f'00000.000000{settings.NUM_PROCESSO_DIVISOR_SUFIXO}0000-00'

    def test_already_clean(self):
        result = mask_processo_eletronico('00000000000000000', clean=False)
        assert result == '00000.000000.0000-00'

    def test_empty_string(self):
        assert mask_processo_eletronico('') == ''


class AnonimizarCpfTest:
    def test_anonimizes_cpf(self):
        assert anonimizar_cpf('00000000000') == '***.000.000-**'

    def test_empty_string(self):
        assert anonimizar_cpf('') == ''


@pytest.mark.parametrize(
    ('documento', 'esperado'),
    [
        ('813.358.734-49', '***.358.734-**'),
        ('ARG-AB123456', 'ARG-****3456'),
        ('SEMDOC-10', 'SEMDOC-10'),
        ('SEMPAIS-10-AB123456', 'SEMPAIS-10-****3456'),
        ('INVALIDO-10-15837026435', 'INVALIDO-10-***.370.264-**'),
        ('CONFLITO-576122-813.358.734-49', 'CONFLITO-576122-***.358.734-**'),
        ('CONFLITO-10-ARG-AB123456', 'CONFLITO-10-ARG-****3456'),
        (None, ''),
    ],
)
def test_anonimizar_documento(documento, esperado):
    assert anonimizar_documento(documento) == esperado


class AnonimizarMatriculaTest:
    def test_anonimizes_matricula(self):
        assert anonimizar_matricula('0000000') == '000****'

    def test_empty_string(self):
        assert anonimizar_matricula('') == ''


class MaskCnpjTest:
    def test_formats_cnpj(self):
        assert mask_cnpj('11444444000132') == '11.444.444/0001-32'

    def test_with_dirty_input(self):
        assert mask_cnpj('11.444.444/0001-32') == '11.444.444/0001-32'


class MaskCepTest:
    def test_formats_cep(self):
        assert mask_cep('99999999') == '99999-999'

    def test_with_dirty_input(self):
        assert mask_cep('99999-999') == '99999-999'


class FormatTelefoneTest:
    def test_8_digit_number(self):
        assert format_telefone('84', '12345678') == '(84) 1234-5678'

    def test_7_digit_number(self):
        assert format_telefone('84', '1234567') == '(84) 123-4567'

    def test_empty_ddd(self):
        assert format_telefone('', '12345678') == '(XX) 1234-5678'

    def test_ddd_with_spaces(self):
        assert format_telefone(' 84 ', '12345678') == '(84) 1234-5678'

    def test_number_with_spaces(self):
        assert format_telefone('84', ' 12345678 ') == '(84) 1234-5678'
