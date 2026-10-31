"""Testes unitários (sem DB) de acessores puros de ``RegistroEmissaoDiploma``.

Cobre formatação (CPF, ingresso) e mapeamentos de status/tipo. FKs e métodos com
acesso a banco são isolados com mocks; nenhum teste toca o banco.
"""

from unittest.mock import Mock, PropertyMock, patch

import pytest

from edu.models.diplomas import RegistroEmissaoDiploma


def _com_aluno(aluno):
    return patch.object(RegistroEmissaoDiploma, 'aluno', new_callable=PropertyMock, return_value=aluno)


# --- get_cpf (slice [4:11]) -------------------------------------------------


def test_get_cpf_retorna_slice_do_meio():
    with _com_aluno(Mock(pessoa_fisica=Mock(cpf='12345678901'))):
        assert RegistroEmissaoDiploma().get_cpf() == '5678901'


def test_get_cpf_vazio_quando_sem_cpf():
    with _com_aluno(Mock(pessoa_fisica=Mock(cpf=''))):
        assert RegistroEmissaoDiploma().get_cpf() == ''


# --- get_ingresso -----------------------------------------------------------


def test_get_ingresso_formata_ano_periodo():
    with _com_aluno(Mock(ano_letivo=2024, periodo_letivo=1)):
        assert RegistroEmissaoDiploma().get_ingresso() == '2024/1'


# --- get_tipo_diploma -------------------------------------------------------


@pytest.mark.parametrize(
    ('eletronica', 'digital', 'esperado'),
    [(True, False, 'Digital'), (False, True, 'Digital'), (True, True, 'Digital'), (False, False, 'Físico')],
)
def test_get_tipo_diploma(eletronica, digital, esperado):
    with (
        patch.object(RegistroEmissaoDiploma, 'is_assinado_eletronicamente', return_value=eletronica),
        patch.object(RegistroEmissaoDiploma, 'is_assinado_digitalmente', return_value=digital),
    ):
        assert RegistroEmissaoDiploma().get_tipo_diploma() == esperado


# --- get_status_situacao ----------------------------------------------------


@pytest.mark.parametrize(
    ('situacao', 'esperado'),
    [('Finalizado', 'success'), (None, 'success'), ('Cancelado', 'error'), ('Em andamento', 'alert')],
)
def test_get_status_situacao(situacao, esperado):
    with patch.object(RegistroEmissaoDiploma, 'get_situacao_display', return_value=situacao):
        assert RegistroEmissaoDiploma().get_status_situacao() == esperado
