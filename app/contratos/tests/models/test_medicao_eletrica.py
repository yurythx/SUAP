from decimal import Decimal

from contratos.models import MedicaoEletrica


class MedicaoEletricaModelLogicTest:
    """Testa as propriedades e métodos de lógica pura do modelo MedicaoEletrica."""

    # demanda_ultrapassada ---------------------------------------------------

    def test_demanda_ultrapassada_quando_medida_maior_que_contratada_retorna_positivo(self):
        """demanda_ultrapassada retorna valor positivo quando medida > contratada."""
        medicao = MedicaoEletrica(
            demanda_medida=Decimal('110'),
            demanda_contratada=Decimal('100'),
        )
        assert medicao.demanda_ultrapassada == Decimal('10')

    def test_demanda_ultrapassada_quando_medida_menor_que_contratada_retorna_negativo(self):
        """demanda_ultrapassada retorna valor negativo quando medida < contratada."""
        medicao = MedicaoEletrica(
            demanda_medida=Decimal('90'),
            demanda_contratada=Decimal('100'),
        )
        assert medicao.demanda_ultrapassada == Decimal('-10')

    def test_demanda_ultrapassada_quando_medida_igual_contratada_retorna_zero(self):
        """demanda_ultrapassada retorna zero quando medida == contratada."""
        medicao = MedicaoEletrica(
            demanda_medida=Decimal('100'),
            demanda_contratada=Decimal('100'),
        )
        assert medicao.demanda_ultrapassada == Decimal('0')

    # percentual_ultrapassado ------------------------------------------------

    def test_percentual_ultrapassado_quando_10_porcento_acima_retorna_10(self):
        """percentual_ultrapassado retorna 10.0 quando demanda está 10% acima."""
        medicao = MedicaoEletrica(
            demanda_medida=Decimal('110'),
            demanda_contratada=Decimal('100'),
        )
        assert medicao.percentual_ultrapassado == Decimal('10.0')

    def test_percentual_ultrapassado_quando_exatamente_contratado_retorna_zero(self):
        """percentual_ultrapassado retorna 0.0 quando demanda medida == contratada."""
        medicao = MedicaoEletrica(
            demanda_medida=Decimal('100'),
            demanda_contratada=Decimal('100'),
        )
        assert medicao.percentual_ultrapassado == Decimal('0.0')

    def test_percentual_ultrapassado_quando_5_porcento_acima_retorna_5(self):
        """percentual_ultrapassado retorna 5.0 quando demanda está 5% acima."""
        medicao = MedicaoEletrica(
            demanda_medida=Decimal('105'),
            demanda_contratada=Decimal('100'),
        )
        assert medicao.percentual_ultrapassado == Decimal('5.0')

    # deve_solicitar_valor_multa ---------------------------------------------

    def test_deve_solicitar_multa_quando_medida_excede_5_porcento_retorna_true(self):
        """deve_solicitar_valor_multa retorna True quando medida > 105% da contratada."""
        medicao = MedicaoEletrica(
            demanda_medida=Decimal('106'),
            demanda_contratada=Decimal('100'),
        )
        assert medicao.deve_solicitar_valor_multa() is True

    def test_deve_solicitar_multa_quando_medida_exatamente_5_porcento_retorna_false(self):
        """deve_solicitar_valor_multa retorna False quando medida é exatamente 105%."""
        medicao = MedicaoEletrica(
            demanda_medida=Decimal('105'),
            demanda_contratada=Decimal('100'),
        )
        assert medicao.deve_solicitar_valor_multa() is False

    def test_deve_solicitar_multa_quando_medida_abaixo_5_porcento_retorna_false(self):
        """deve_solicitar_valor_multa retorna False quando medida < 105% da contratada."""
        medicao = MedicaoEletrica(
            demanda_medida=Decimal('104'),
            demanda_contratada=Decimal('100'),
        )
        assert medicao.deve_solicitar_valor_multa() is False

    def test_deve_solicitar_multa_quando_demanda_medida_none_retorna_false(self):
        """deve_solicitar_valor_multa retorna False quando demanda_medida é None."""
        medicao = MedicaoEletrica(
            demanda_medida=None,
            demanda_contratada=Decimal('100'),
        )
        assert medicao.deve_solicitar_valor_multa() is False

    def test_deve_solicitar_multa_quando_demanda_contratada_none_retorna_false(self):
        """deve_solicitar_valor_multa retorna False quando demanda_contratada é None."""
        medicao = MedicaoEletrica(
            demanda_medida=Decimal('100'),
            demanda_contratada=None,
        )
        assert medicao.deve_solicitar_valor_multa() is False

    def test_deve_solicitar_multa_quando_demanda_medida_zero_retorna_false(self):
        """deve_solicitar_valor_multa retorna False quando demanda_medida é zero."""
        medicao = MedicaoEletrica(
            demanda_medida=Decimal('0'),
            demanda_contratada=Decimal('100'),
        )
        assert medicao.deve_solicitar_valor_multa() is False

    def test_deve_solicitar_multa_quando_demanda_contratada_zero_retorna_false(self):
        """deve_solicitar_valor_multa retorna False quando demanda_contratada é zero."""
        medicao = MedicaoEletrica(
            demanda_medida=Decimal('100'),
            demanda_contratada=Decimal('0'),
        )
        assert medicao.deve_solicitar_valor_multa() is False
