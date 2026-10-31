import pytest
from django.forms import ValidationError

from djtools.forms.fields import BrCpfCnpjField, BrCpfField
from djtools.utils.validators import cnpj_valido, cpf_valido, email_valido

SEQUENCIAS_REPETIDAS = [d * 11 for d in '0123456789']
CNPJS_REPETIDOS = [d * 14 for d in '0123456789'] + ['00.000.000/0000-00']


class TestCpfValido:
    def test_valid_cpf_returns_true(self) -> None:
        assert cpf_valido('123.456.789-09') is True

    def test_valid_cpf_with_only_digits_returns_true(self) -> None:
        assert cpf_valido('12345678909') is True

    def test_invalid_cpf_returns_false(self) -> None:
        assert cpf_valido('123.456.789-00') is False

    def test_cpf_with_wrong_digits_returns_false(self) -> None:
        assert cpf_valido('123.456.789-01') is False

    def test_empty_string_returns_false(self) -> None:
        assert cpf_valido('') is False

    @pytest.mark.parametrize('cpf', SEQUENCIAS_REPETIDAS)
    def test_sequencia_repetida_returns_false(self, cpf: str) -> None:
        # #17410: o cálculo do DV fecha para 111.111.111-11 & cia.; a Receita não emite esses números.
        assert cpf_valido(cpf) is False


class TestBrCpfField:
    @pytest.mark.parametrize('cpf', ['111.111.111-11', '00000000000'])
    def test_recusa_sequencia_repetida(self, cpf: str) -> None:
        with pytest.raises(ValidationError, match='informar um CPF válido'):
            BrCpfField().clean(cpf)

    def test_aceita_cpf_valido(self) -> None:
        assert BrCpfField().clean('12345678909') == '123.456.789-09'


class TestBrCpfCnpjField:
    def test_recusa_cpf_com_sequencia_repetida(self) -> None:
        with pytest.raises(ValidationError):
            BrCpfCnpjField().clean('11111111111')

    def test_aceita_cpf_valido(self) -> None:
        assert BrCpfCnpjField().clean('12345678909') == '123.456.789-09'

    def test_recusa_cnpj_com_sequencia_repetida(self) -> None:
        with pytest.raises(ValidationError):
            BrCpfCnpjField().clean('00000000000000')


class TestCnpjValido:
    def test_valid_cnpj_returns_true(self) -> None:
        assert cnpj_valido('11.444.444/0001-32') is True

    @pytest.mark.parametrize('cnpj', CNPJS_REPETIDOS)
    def test_sequencia_repetida_returns_false(self, cnpj: str) -> None:
        # #17410: 00.000.000/0000-00 fecha o cálculo do DV, mas não é CNPJ.
        assert cnpj_valido(cnpj) is False

    def test_valid_cnpj_with_only_digits_returns_true(self) -> None:
        assert cnpj_valido('11444444000132') is True

    def test_invalid_cnpj_returns_false(self) -> None:
        assert cnpj_valido('11.444.444/0001-94') is False

    def test_cnpj_with_wrong_digits_returns_false(self) -> None:
        assert cnpj_valido('11.444.444/0001-99') is False

    def test_empty_string_returns_false(self) -> None:
        assert cnpj_valido('') is False


class TestEmailValido:
    def test_valid_email_returns_true(self) -> None:
        assert email_valido('user@example.com') is True

    def test_email_with_plus_returns_true(self) -> None:
        assert email_valido('user+tag@example.com') is True

    def test_invalid_email_returns_false(self) -> None:
        assert email_valido('not-an-email') is False

    def test_empty_string_returns_false(self) -> None:
        assert email_valido('') is False

    def test_email_without_domain_returns_false(self) -> None:
        assert email_valido('user@.com') is False
