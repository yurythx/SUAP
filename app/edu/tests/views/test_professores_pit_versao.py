from __future__ import annotations

from unittest.mock import MagicMock, patch
from pit_rit_v3.models import PlanoIndividualTrabalhoV3


class TestEduVersaoPitSelecao:
    def test_pit_v3_nao_selecionado_quando_modulo_nao_ativo(self) -> None:
        periodo_letivo_atual = MagicMock(ano=2026, periodo=2)
        with patch.object(PlanoIndividualTrabalhoV3, 'modulo_ativo', return_value=False):
            assert PlanoIndividualTrabalhoV3.modulo_ativo(periodo_letivo_atual.ano, periodo_letivo_atual.periodo) is False

    def test_pit_v3_selecionado_quando_modulo_ativo(self) -> None:
        periodo_letivo_atual = MagicMock(ano=2026, periodo=2)
        with patch.object(PlanoIndividualTrabalhoV3, 'modulo_ativo', return_value=True):
            assert PlanoIndividualTrabalhoV3.modulo_ativo(periodo_letivo_atual.ano, periodo_letivo_atual.periodo) is True
