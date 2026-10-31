"""Testes unitários (sem DB) de ``validar_matricula_de_aluno_em_diario`` (``edu/utils.py``).

Cobre os guard-clauses puros (aluno/diário ausentes) e a propagação da mensagem
quando o aluno não pode ser matriculado — tudo com mocks leves, sem banco.
"""

from unittest.mock import Mock

import pytest
from django.core.exceptions import ValidationError

from edu.utils import validar_matricula_de_aluno_em_diario


def test_aluno_none_levanta_validation_error():
    with pytest.raises(ValidationError, match='aluno não foi informado'):
        validar_matricula_de_aluno_em_diario(None, Mock())


def test_diario_none_levanta_validation_error():
    with pytest.raises(ValidationError, match='diário não foi informado'):
        validar_matricula_de_aluno_em_diario(Mock(), None)


def test_aluno_impedido_propaga_mensagem_de_validacao():
    aluno = Mock()
    aluno.pode_ser_matriculado_no_diario.return_value = (False, 'motivo do impedimento')

    with pytest.raises(ValidationError, match='motivo do impedimento'):
        validar_matricula_de_aluno_em_diario(aluno, Mock())

    aluno.pode_ser_matriculado_no_diario.assert_called_once()
