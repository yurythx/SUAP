"""Testes unitários (sem DB) dos cálculos puros de ``MatriculaDiario``.

Padrão: instanciar o model em memória e isolar os acessos a FK/manager com mocks
leves (ver ``test_alunos.py``). Nenhum teste aqui usa ``suap_data``/``django_db`` —
o arquivo é não-legado, então o gate ``auto_db`` (``conftest.py``) nunca dispara.
"""

from unittest.mock import Mock, PropertyMock, patch

import pytest

from edu.models.cursos import EstruturaCurso
from edu.models.historico import MatriculaDiario


def _diario_mock(qtd_avaliacoes=1, ponderada=True):
    """Mock de ``self.diario`` cobrindo os atributos lidos pelos cálculos."""
    diario = Mock()
    diario.componente_curricular.qtd_avaliacoes = qtd_avaliacoes
    diario.estrutura_curso.calculo_media_final = EstruturaCurso.MEDIA_FINAL_PONDERADA if ponderada else EstruturaCurso.MEDIA_FINAL_ARITMETICA
    return diario


def _matricula(**notas):
    """Cria ``MatriculaDiario`` em memória com as notas dadas (``diario`` é mockado pelo teste)."""
    md = MatriculaDiario()
    for campo, valor in notas.items():
        setattr(md, campo, valor)
    return md


# --- get_pesos_calculo_media ------------------------------------------------


def test_pesos_ponderada_retorna_2_e_3():
    with patch.object(MatriculaDiario, 'diario', new_callable=PropertyMock) as diario:
        diario.return_value = _diario_mock(ponderada=True)
        assert MatriculaDiario().get_pesos_calculo_media() == (2, 3)


def test_pesos_nao_ponderada_retorna_1_e_1():
    with patch.object(MatriculaDiario, 'diario', new_callable=PropertyMock) as diario:
        diario.return_value = _diario_mock(ponderada=False)
        assert MatriculaDiario().get_pesos_calculo_media() == (1, 1)


# --- get_media_disciplina ---------------------------------------------------


def test_media_disciplina_uma_avaliacao_retorna_a_propria_nota():
    with patch.object(MatriculaDiario, 'diario', new_callable=PropertyMock) as diario:
        diario.return_value = _diario_mock(qtd_avaliacoes=1)
        md = _matricula(nota_1=9)
        assert md.get_media_disciplina() == 9


def test_media_disciplina_duas_avaliacoes_ponderada():
    # P1=2, P2=3, divisor=5 -> (2*10 + 3*5) / 5 = 7
    with patch.object(MatriculaDiario, 'diario', new_callable=PropertyMock) as diario:
        diario.return_value = _diario_mock(qtd_avaliacoes=2, ponderada=True)
        md = _matricula(nota_1=10, nota_2=5)
        assert md.get_media_disciplina() == 7


def test_media_disciplina_duas_avaliacoes_aritmetica():
    # P1=P2=1, divisor=2 -> (8 + 6) / 2 = 7
    with patch.object(MatriculaDiario, 'diario', new_callable=PropertyMock) as diario:
        diario.return_value = _diario_mock(qtd_avaliacoes=2, ponderada=False)
        md = _matricula(nota_1=8, nota_2=6)
        assert md.get_media_disciplina() == 7


def test_media_disciplina_tres_avaliacoes_media_aritmetica():
    # (6 + 7 + 8) / 3 = 7
    with patch.object(MatriculaDiario, 'diario', new_callable=PropertyMock) as diario:
        diario.return_value = _diario_mock(qtd_avaliacoes=3)
        md = _matricula(nota_1=6, nota_2=7, nota_3=8)
        assert md.get_media_disciplina() == 7


def test_media_disciplina_quatro_avaliacoes_ponderada():
    # divisor=2*(2+3)=10 -> (2*10 + 2*10 + 3*5 + 3*5) / 10 = 7
    with patch.object(MatriculaDiario, 'diario', new_callable=PropertyMock) as diario:
        diario.return_value = _diario_mock(qtd_avaliacoes=4, ponderada=True)
        md = _matricula(nota_1=10, nota_2=10, nota_3=5, nota_4=5)
        assert md.get_media_disciplina() == 7


@pytest.mark.parametrize(
    ('qtd_avaliacoes', 'nota_ausente'),
    [(2, 'nota_1'), (2, 'nota_2'), (3, 'nota_3'), (4, 'nota_4')],
)
def test_media_disciplina_retorna_none_quando_nota_esperada_ausente(qtd_avaliacoes, nota_ausente):
    notas: dict[str, int | None] = {'nota_1': 8, 'nota_2': 6, 'nota_3': 7, 'nota_4': 9}
    notas[nota_ausente] = None
    with patch.object(MatriculaDiario, 'diario', new_callable=PropertyMock) as diario:
        diario.return_value = _diario_mock(qtd_avaliacoes=qtd_avaliacoes)
        md = _matricula(**notas)
        assert md.get_media_disciplina() is None


# --- calcular_media_etapa_com_recuperacao -----------------------------------


def _notas_recuperacao(nota):
    """Queryset mockado cujo ``.first()`` devolve um registro com ``.nota``."""
    qs = Mock()
    qs.first.return_value = None if nota is None else Mock(nota=nota)
    return qs


def test_recuperacao_maior_que_media_substitui():
    md = MatriculaDiario()
    assert md.calcular_media_etapa_com_recuperacao(_notas_recuperacao(8), media_etapa=5) == 8


def test_recuperacao_menor_ou_igual_mantem_media():
    md = MatriculaDiario()
    assert md.calcular_media_etapa_com_recuperacao(_notas_recuperacao(4), media_etapa=7) == 7


def test_sem_nota_de_recuperacao_mantem_media():
    md = MatriculaDiario()
    assert md.calcular_media_etapa_com_recuperacao(_notas_recuperacao(None), media_etapa=6) == 6


def test_recuperacao_zero_e_falsy_mantem_media():
    md = MatriculaDiario()
    assert md.calcular_media_etapa_com_recuperacao(_notas_recuperacao(0), media_etapa=5) == 5


def test_media_etapa_none_sem_recuperacao_retorna_zero():
    md = MatriculaDiario()
    assert md.calcular_media_etapa_com_recuperacao(_notas_recuperacao(None), media_etapa=None) == 0
