from __future__ import annotations

import datetime
from unittest.mock import Mock, patch

from edu.models.alunos import Aluno
from edu.models.cadastros_gerais import Modalidade
from edu.models.cursos import CursoCampus, EstruturaCurso, Matriz


def test_data_prevista_termino_retorna_valor_preenchido() -> None:
    aluno = Aluno()
    data_manual = datetime.date(2027, 6, 30)
    aluno.data_prevista_termino_ciclo = data_manual
    assert aluno.data_prevista_termino_ciclo == data_manual


def test_data_prevista_termino_minicurso_usa_data_fim_da_turma() -> None:
    curso = CursoCampus(modalidade_id=Modalidade.FIC_MENOS, ch_total=CursoCampus.CARGA_HORARIA_BASE_MINICURSO)
    aluno = Aluno(id=123, curso_campus=curso)

    with patch('edu.models.alunos.ParticipanteTurmaMinicurso.objects.filter') as filter_mock:
        filter_mock.return_value.order_by.return_value.values_list.return_value.first.return_value = datetime.date(2026, 5, 20)
        data_fim = aluno.calcular_data_prevista_termino_ciclo()
        assert data_fim == datetime.date(2026, 5, 20)
        filter_mock.assert_called_once_with(aluno_id=123)


def test_data_prevista_termino_minicurso_sem_turma_retorna_none() -> None:
    curso = CursoCampus(modalidade_id=Modalidade.FIC_MENOS, ch_total=CursoCampus.CARGA_HORARIA_BASE_MINICURSO)
    aluno = Aluno(id=None, curso_campus=curso)
    assert aluno.calcular_data_prevista_termino_ciclo() is None


def test_data_prevista_termino_minicurso_sem_participante_retorna_none() -> None:
    curso = CursoCampus(modalidade_id=Modalidade.FIC_MENOS, ch_total=CursoCampus.CARGA_HORARIA_BASE_MINICURSO)
    aluno = Aluno(id=123, curso_campus=curso)

    with patch('edu.models.alunos.ParticipanteTurmaMinicurso.objects.filter') as filter_mock:
        filter_mock.return_value.order_by.return_value.values_list.return_value.first.return_value = None
        assert aluno.calcular_data_prevista_termino_ciclo() is None


def test_data_prevista_termino_minicurso_nao_apto_sistec_retorna_none() -> None:
    curso = CursoCampus(modalidade_id=Modalidade.FIC_MENOS, ch_total=CursoCampus.CARGA_HORARIA_BASE_MINICURSO - 1)
    aluno = Aluno(id=123, curso_campus=curso)
    assert aluno.calcular_data_prevista_termino_ciclo() is None


def test_data_prevista_termino_curso_semestral() -> None:
    matriz = Matriz(qtd_periodos_letivos=4)
    curso = CursoCampus(
        periodicidade=CursoCampus.PERIODICIDADE_SEMESTRAL,
        modalidade_id=Modalidade.TECNOLOGIA,
        descricao='TSI',
    )
    aluno = Aluno(
        curso_campus=curso,
        matriz=matriz,
        data_inicio_ciclo=datetime.date(2024, 2, 1),
    )
    # 4 períodos * 6 meses = 24 meses (2 anos) -> 2024-02-01 + 24 meses = 2026-02-01
    assert aluno.calcular_data_prevista_termino_ciclo() == datetime.date(2026, 2, 1)


def test_data_prevista_termino_curso_anual() -> None:
    matriz = Matriz(qtd_periodos_letivos=3)
    curso = CursoCampus(
        periodicidade=CursoCampus.PERIODICIDADE_ANUAL,
        modalidade_id=Modalidade.INTEGRADO,
        descricao='Técnico em Informática Integrado',
    )
    aluno = Aluno(
        curso_campus=curso,
        matriz=matriz,
        data_inicio_ciclo=datetime.date(2023, 3, 1),
    )
    # 3 períodos anuais = 3 anos -> 2023-03-01 + 3 anos = 2026-03-01
    assert aluno.calcular_data_prevista_termino_ciclo() == datetime.date(2026, 3, 1)


def test_data_prevista_termino_calcula_data_inicio_se_nula() -> None:
    matriz = Matriz(qtd_periodos_letivos=2)
    curso = CursoCampus(
        periodicidade=CursoCampus.PERIODICIDADE_SEMESTRAL,
        modalidade_id=Modalidade.SUBSEQUENTE,
        descricao='Subsequente Edificações',
    )
    aluno = Aluno(
        curso_campus=curso,
        matriz=matriz,
        data_inicio_ciclo=None,
    )
    aluno.calcular_data_inicio_ciclo = Mock(return_value=datetime.date(2025, 1, 15))
    assert aluno.calcular_data_prevista_termino_ciclo() == datetime.date(2026, 1, 15)


def test_data_prevista_termino_sem_matriz_retorna_none() -> None:
    curso = CursoCampus(modalidade_id=Modalidade.INTEGRADO, descricao='Curso')
    aluno = Aluno(
        curso_campus=curso,
        matriz=None,
        data_inicio_ciclo=datetime.date(2025, 1, 15),
    )
    assert aluno.calcular_data_prevista_termino_ciclo() is None


def test_aluno_pode_emitir_declaracao_retorna_estritamente_booleano() -> None:
    estrutura = EstruturaCurso(proitec=False)
    matriz = Matriz(estrutura=estrutura)
    curso = CursoCampus(modalidade_id=Modalidade.INTEGRADO)
    aluno = Aluno(matriz=matriz, curso_campus=curso)

    resultado = aluno.pode_emitir_declaracao()
    assert resultado is True
    assert type(resultado) is bool
