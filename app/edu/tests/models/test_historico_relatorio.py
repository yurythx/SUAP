"""Testes unitários (sem DB) das URLs de ``HistoricoRelatorio`` (``edu/models/utils.py``).

Lógica in-memory: ``get_url_sem_parametro`` indexa ``URL_CHOICES`` por ``tipo`` e
``get_url`` decodifica ``query_string`` (hex) — nada toca o banco.
"""

import pytest

from edu.models.utils import HistoricoRelatorio


@pytest.mark.parametrize(
    ('tipo', 'caminho'),
    [
        (HistoricoRelatorio.TIPO_ALUNO, '/edu/relatorio/'),
        (HistoricoRelatorio.TIPO_DIARIO, '/edu/relatorio_diario/'),
        (HistoricoRelatorio.TIPO_PROFESSOR, '/edu/relatorio_professor/'),
    ],
)
def test_url_sem_parametro_mapeia_tipo_para_caminho(tipo, caminho):
    assert HistoricoRelatorio(tipo=tipo).get_url_sem_parametro() == caminho


def test_get_url_anexa_query_string_decodificada_de_hex():
    # 'a=1&b=2' em hex
    query_string_hex = b'a=1&b=2'.hex()
    historico = HistoricoRelatorio(tipo=HistoricoRelatorio.TIPO_ALUNO, query_string=query_string_hex)
    assert historico.get_url() == '/edu/relatorio/?a=1&b=2'
