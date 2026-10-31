import pytest

from edu.models.cadastros_gerais import SituacaoMatriculaPeriodo


@pytest.mark.parametrize(
    ('situacao_id', 'esperado'),
    [
        (9999, 'OutraSituacao'),
        (SituacaoMatriculaPeriodo.AFASTADO, 'Licenca'),
        (SituacaoMatriculaPeriodo.MATRICULADO, 'MatriculadoEmDisciplina'),
        (SituacaoMatriculaPeriodo.JUBILADO, 'Jubilado'),
        (SituacaoMatriculaPeriodo.INTERCAMBIO, 'IntercambioInternacional'),
        (SituacaoMatriculaPeriodo.EVASAO, 'Abandono'),
        (SituacaoMatriculaPeriodo.TRANSF_EXTERNA, ('Desistencia',)),
    ],
)
def test_get_situacao_diploma_digital_retorna_classificacao_esperada(situacao_id, esperado):
    situacao = SituacaoMatriculaPeriodo(id=situacao_id)

    assert situacao.get_situacao_diploma_digital() == esperado
