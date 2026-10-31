from django.core.exceptions import ValidationError

from contratos.models import Contrato
import pytest


class ContratoCleanNumeroTest:
    """Testa o método clean_numero do modelo Contrato."""

    # clean_numero: formatação -------------------------------------------------

    def test_clean_numero_com_1_digito_formata_para_5_digitos(self):
        """clean_numero formata '1/2024' para '00001/2024'."""
        contrato = Contrato(numero='1/2024')
        contrato.clean_numero()
        assert contrato.numero == '00001/2024'

    def test_clean_numero_com_5_digitos_mantem_valor(self):
        """clean_numero mantém '12345/2024' inalterado."""
        contrato = Contrato(numero='12345/2024')
        contrato.clean_numero()
        assert contrato.numero == '12345/2024'

    def test_clean_numero_com_3_digitos_formata_para_5_digitos(self):
        """clean_numero formata '123/2023' para '00123/2023'."""
        contrato = Contrato(numero='123/2023')
        contrato.clean_numero()
        assert contrato.numero == '00123/2023'

    # clean_numero: validação --------------------------------------------------

    def test_clean_numero_com_formato_invalido_abc_lanca_validation_error(self):
        """clean_numero levanta ValidationError para 'abc'."""
        contrato = Contrato(numero='abc')
        with pytest.raises(ValidationError):
            contrato.clean_numero()

    def test_clean_numero_com_formato_invalido_sem_barra_lanca_validation_error(self):
        """clean_numero levanta ValidationError para '123' (sem barra)."""
        contrato = Contrato(numero='123')
        with pytest.raises(ValidationError):
            contrato.clean_numero()

    def test_clean_numero_com_ano_2_digitos_lanca_validation_error(self):
        """clean_numero levanta ValidationError para '123/23' (ano com 2 dígitos)."""
        contrato = Contrato(numero='123/23')
        with pytest.raises(ValidationError):
            contrato.clean_numero()

    def test_clean_numero_com_numero_6_digitos_lanca_validation_error(self):
        """clean_numero levanta ValidationError para '123456/2024' (mais de 5 dígitos)."""
        contrato = Contrato(numero='123456/2024')
        with pytest.raises(ValidationError):
            contrato.clean_numero()
