from contratos.models import Aditivo


class AditivoGetTipoTest:
    """Testa o método get_tipo do modelo Aditivo."""

    def test_get_tipo_quando_de_prazo_retorna_de_prazo(self):
        """get_tipo retorna 'de Prazo' quando apenas de_prazo=True."""
        aditivo = Aditivo(de_prazo=True)
        assert aditivo.get_tipo() == 'de Prazo'

    def test_get_tipo_quando_de_valor_retorna_de_valor(self):
        """get_tipo retorna 'de Valor' quando apenas de_valor=True."""
        aditivo = Aditivo(de_valor=True)
        assert aditivo.get_tipo() == 'de Valor'

    def test_get_tipo_quando_de_fiscal_retorna_de_fiscal(self):
        """get_tipo retorna 'de Fiscal' quando apenas de_fiscal=True."""
        aditivo = Aditivo(de_fiscal=True)
        assert aditivo.get_tipo() == 'de Fiscal'

    def test_get_tipo_quando_de_outro_retorna_de_outro(self):
        """get_tipo retorna 'de Outro' quando apenas de_outro=True."""
        aditivo = Aditivo(de_outro=True)
        assert aditivo.get_tipo() == 'de Outro'

    def test_get_tipo_quando_prazo_e_valor_retorna_ambos(self):
        """get_tipo retorna 'de Prazo, de Valor' quando ambos True."""
        aditivo = Aditivo(de_prazo=True, de_valor=True)
        assert aditivo.get_tipo() == 'de Prazo, de Valor'

    def test_get_tipo_quando_todos_true_retorna_todos(self):
        """get_tipo retorna 'de Prazo, de Valor, de Fiscal, de Outro' quando todos True."""
        aditivo = Aditivo(de_prazo=True, de_valor=True, de_fiscal=True, de_outro=True)
        assert aditivo.get_tipo() == 'de Prazo, de Valor, de Fiscal, de Outro'

    def test_get_tipo_quando_nenhum_retorna_indefinido(self):
        """get_tipo retorna 'Indefinido' quando todas as flags sao False."""
        aditivo = Aditivo()
        assert aditivo.get_tipo() == 'Indefinido'

    def test_get_tipo_quando_prazo_fiscal_outro_retorna_tres(self):
        """get_tipo retorna combinacao correta com 3 flags True."""
        aditivo = Aditivo(de_prazo=True, de_fiscal=True, de_outro=True)
        assert aditivo.get_tipo() == 'de Prazo, de Fiscal, de Outro'
