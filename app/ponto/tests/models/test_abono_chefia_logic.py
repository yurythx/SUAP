from ponto.models import AbonoChefia, SolicitacaoAbonoParcial


class TestAbonoChefiaEhAbonoParcial:
    """Testes para a propriedade ``eh_abono_parcial``."""

    def test_quando_possui_solicitacao_abono_parcial(self):
        """Deve retornar True quando ``solicitacao_abono_parcial`` está definido."""
        abono_parcial = SolicitacaoAbonoParcial()
        abono = AbonoChefia(solicitacao_abono_parcial=abono_parcial)
        assert abono.eh_abono_parcial is True

    def test_quando_nao_possui_solicitacao_abono_parcial(self):
        """Deve retornar False quando ``solicitacao_abono_parcial`` é None."""
        abono = AbonoChefia()
        assert abono.eh_abono_parcial is False


class TestAbonoChefiaChAbonadaParcialmenteDisplay:
    """Testes para a propriedade ``ch_abonada_parcialmente_display``."""

    def test_quando_sem_solicitacao_abono_parcial(self):
        """Deve retornar None quando ``solicitacao_abono_parcial`` é None."""
        abono = AbonoChefia()
        assert abono.ch_abonada_parcialmente_display is None


class TestAbonoChefiaChAbonadaParcialmenteDisplay2:
    """Testes para a propriedade ``ch_abonada_parcialmente_display_2``."""

    def test_quando_sem_solicitacao_abono_parcial(self):
        """Deve retornar None quando ``solicitacao_abono_parcial`` é None."""
        abono = AbonoChefia()
        assert abono.ch_abonada_parcialmente_display_2 is None


class TestAbonoChefiaChDescontadaDisplay:
    """Testes para a propriedade ``ch_descontada_display``."""

    def test_com_ch_descontada_3600(self):
        """Deve retornar '1h 0min 0seg' para 3600 segundos."""
        abono = AbonoChefia(ch_descontada=3600)
        assert abono.ch_descontada_display == '1h 0min 0seg'

    def test_com_ch_descontada_none(self):
        """Deve retornar None quando ``ch_descontada`` é None."""
        abono = AbonoChefia(ch_descontada=None)
        assert abono.ch_descontada_display is None

    def test_com_ch_descontada_zero(self):
        """Deve retornar None quando ``ch_descontada`` é 0 (falsy)."""
        abono = AbonoChefia(ch_descontada=0)
        assert abono.ch_descontada_display is None


class TestAbonoChefiaChDescontadaDisplay2:
    """Testes para a propriedade ``ch_descontada_display_2``."""

    def test_com_ch_descontada_3600(self):
        """Deve retornar '1h' para 3600 segundos (omitindo zeros)."""
        abono = AbonoChefia(ch_descontada=3600)
        assert abono.ch_descontada_display_2 == '1h'

    def test_com_ch_descontada_none(self):
        """Deve retornar None quando ``ch_descontada`` é None."""
        abono = AbonoChefia(ch_descontada=None)
        assert abono.ch_descontada_display_2 is None
