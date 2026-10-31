from decimal import Decimal

from contratos.models import Contrato


class ContratoEhContinuoTest:
    """Testa a propriedade eh_continuo do modelo Contrato."""

    def test_eh_continuo_quando_continuidade_continuo_retorna_true(self):
        """eh_continuo retorna True quando continuidade == CONTINUO."""
        contrato = Contrato(continuidade='CONTINUO')
        assert contrato.eh_continuo is True

    def test_eh_continuo_quando_continuidade_escopo_retorna_false(self):
        """eh_continuo retorna False quando continuidade == ESCOPO."""
        contrato = Contrato(continuidade='ESCOPO')
        assert contrato.eh_continuo is False

    def test_eh_continuo_quando_continuidade_indeterminado_retorna_false(self):
        """eh_continuo retorna False quando continuidade == INDETERMINADO."""
        contrato = Contrato(continuidade='INDETERMINADO')
        assert contrato.eh_continuo is False

    def test_eh_continuo_quando_continuidade_none_retorna_none(self):
        """eh_continuo retorna None quando continuidade é None."""
        contrato = Contrato(continuidade=None)
        assert contrato.eh_continuo is None


class ContratoPossuiArrecadacaoReceitaTest:
    """Testa a propriedade possui_arrecadacao_receita do modelo Contrato."""

    def test_possui_arrecadacao_quando_natureza_receita_retorna_true(self):
        """possui_arrecadacao_receita retorna True quando natureza == RECEITA."""
        contrato = Contrato(natureza='RECEITA')
        assert contrato.possui_arrecadacao_receita is True

    def test_possui_arrecadacao_quando_natureza_receita_despesa_retorna_true(self):
        """possui_arrecadacao_receita retorna True quando natureza == RECEITA_DESPESA."""
        contrato = Contrato(natureza='RECEITA_DESPESA')
        assert contrato.possui_arrecadacao_receita is True

    def test_possui_arrecadacao_quando_natureza_despesa_retorna_false(self):
        """possui_arrecadacao_receita retorna False quando natureza == DESPESA."""
        contrato = Contrato(natureza='DESPESA')
        assert contrato.possui_arrecadacao_receita is False

    def test_possui_arrecadacao_quando_natureza_none_retorna_none(self):
        """possui_arrecadacao_receita retorna None quando natureza é None."""
        contrato = Contrato(natureza=None)
        assert contrato.possui_arrecadacao_receita is None


class ContratoGetPercentualExecutadoTest:
    """Testa o método get_percentual_executado do modelo Contrato."""

    def test_percentual_quando_valor_total_zero_retorna_zero(self):
        """get_percentual_executado retorna 0 quando valor_total é 0."""
        contrato = Contrato(valor_total=Decimal('0'), valor_executado=Decimal('50'))
        assert contrato.get_percentual_executado() == 0

    def test_percentual_quando_valor_executado_zero_retorna_zero(self):
        """get_percentual_executado retorna 0 quando valor_executado é 0."""
        contrato = Contrato(valor_total=Decimal('200'), valor_executado=Decimal('0'))
        assert contrato.get_percentual_executado() == 0

    def test_percentual_quando_25_porcento_executado_retorna_25(self):
        """get_percentual_executado retorna 25 para 50/200."""
        contrato = Contrato(valor_total=Decimal('200'), valor_executado=Decimal('50'))
        assert contrato.get_percentual_executado() == 25

    def test_percentual_quando_100_porcento_executado_retorna_100(self):
        """get_percentual_executado retorna 100 quando totalmente executado."""
        contrato = Contrato(valor_total=Decimal('200'), valor_executado=Decimal('200'))
        assert contrato.get_percentual_executado() == 100

    def test_percentual_quando_mais_de_100_porcento_retorna_int_truncado(self):
        """get_percentual_executado retorna int truncado (nao arredondado)."""
        contrato = Contrato(valor_total=Decimal('300'), valor_executado=Decimal('100'))
        assert contrato.get_percentual_executado() == 33
