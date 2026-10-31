"""Cada faixa de ``duracao_psiquiatria`` tem rótulo próprio (#17780): 2 e 3 mostravam o mesmo texto."""

import pytest

from saude.models import DuracaoPsiquiatria, ProcessoSaudeDoenca


@pytest.mark.parametrize(
    ('valor', 'rotulo'),
    [(DuracaoPsiquiatria.ENTRE_1_2_ANOS, 'Entre 1 e 2 anos'), (DuracaoPsiquiatria.ENTRE_2_3_ANOS, 'Entre 2 e 3 anos')],
)
def test_rotulo_da_duracao_psiquiatria(valor: int, rotulo: str) -> None:
    assert ProcessoSaudeDoenca(duracao_psiquiatria=valor).get_duracao_psiquiatria_display() == rotulo
