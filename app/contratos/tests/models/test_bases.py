from contratos.models import BaseLegal


class BaseLegalTempoMaximoProrrogacaoTest:
    """Testa a propriedade tempo_maximo_prorrogacao do modelo BaseLegal."""

    def test_tempo_maximo_quando_vigencia_60_prorrogacao_12_retorna_72(self):
        """tempo_maximo_prorrogacao retorna 72 quando vigencia=60 e prorrogacao=12."""
        base = BaseLegal(vigencia=60, prorrogacao=12)
        assert base.tempo_maximo_prorrogacao == 72

    def test_tempo_maximo_quando_vigencia_0_prorrogacao_12_retorna_12(self):
        """tempo_maximo_prorrogacao retorna 12 quando vigencia=0 e prorrogacao=12."""
        base = BaseLegal(vigencia=0, prorrogacao=12)
        assert base.tempo_maximo_prorrogacao == 12

    def test_tempo_maximo_quando_vigencia_60_prorrogacao_0_retorna_60(self):
        """tempo_maximo_prorrogacao retorna 60 quando vigencia=60 e prorrogacao=0."""
        base = BaseLegal(vigencia=60, prorrogacao=0)
        assert base.tempo_maximo_prorrogacao == 60

    def test_tempo_maximo_quando_vigencia_none_prorrogacao_12_retorna_12(self):
        """tempo_maximo_prorrogacao retorna 12 quando vigencia=None e prorrogacao=12."""
        base = BaseLegal(vigencia=None, prorrogacao=12)
        assert base.tempo_maximo_prorrogacao == 12

    def test_tempo_maximo_quando_vigencia_60_prorrogacao_none_retorna_60(self):
        """tempo_maximo_prorrogacao retorna 60 quando vigencia=60 e prorrogacao=None."""
        base = BaseLegal(vigencia=60, prorrogacao=None)
        assert base.tempo_maximo_prorrogacao == 60

    def test_tempo_maximo_quando_ambos_none_retorna_0(self):
        """tempo_maximo_prorrogacao retorna 0 quando vigencia=None e prorrogacao=None."""
        base = BaseLegal(vigencia=None, prorrogacao=None)
        assert base.tempo_maximo_prorrogacao == 0
