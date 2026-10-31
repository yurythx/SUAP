"""Tests for beat.models — ResultadoExecucao model methods."""

from unittest import mock

import pytest

from beat.models import ResultadoExecucao


@pytest.fixture
def resultado():
    return ResultadoExecucao.objects.create(
        command_name='test_command',
        status=ResultadoExecucao.STATUS_PENDING,
    )


@pytest.mark.django_db
def test_str_representation(resultado):
    expected = f'Comando "test_command" executado às {resultado.datetime_start}'
    assert str(resultado) == expected


@pytest.mark.django_db
def test_get_stdout_display_with_content(resultado):
    resultado.stdout = 'some output'
    assert resultado.get_stdout_display() == '<pre>some output</pre>'


@pytest.mark.django_db
def test_get_stdout_display_without_content(resultado):
    assert resultado.get_stdout_display() == 'Nenhuma saída padrão'


@pytest.mark.django_db
def test_get_stderr_display_with_content(resultado):
    resultado.stderr = 'some error'
    assert resultado.get_stderr_display() == '<pre>some error</pre>'


@pytest.mark.django_db
def test_get_stderr_display_without_content(resultado):
    assert resultado.get_stderr_display() == 'Nenhuma saída de erro'


@pytest.mark.django_db
@pytest.mark.parametrize(
    ('status', 'expected_label'),
    [
        (ResultadoExecucao.STATUS_PENDING, 'Pendente'),
        (ResultadoExecucao.STATUS_RUNNING, 'Executando'),
        (ResultadoExecucao.STATUS_SUCCESS, 'Sucesso'),
        (ResultadoExecucao.STATUS_FAILED, 'Falha'),
        (ResultadoExecucao.STATUS_TIMEOUT, 'Timeout'),
        (ResultadoExecucao.STATUS_REVOKED, 'Revogado'),
    ],
)
def test_get_status_display_known_status(resultado, status, expected_label):
    resultado.status = status
    assert resultado.get_status_display() == expected_label


@pytest.mark.django_db
def test_get_status_display_unknown_status(resultado):
    resultado.status = 'UNKNOWN_STATUS'
    assert resultado.get_status_display() == 'Desconhecido'


@pytest.mark.django_db
def test_revoke_with_task_id(resultado):
    resultado.task_id = 'task-123'
    resultado.save()
    with mock.patch('beat.models.app.control.revoke') as mock_revoke:
        result = resultado.revoke()
        mock_revoke.assert_called_once_with('task-123', terminate=True)
    assert result is True
    resultado.refresh_from_db()
    assert resultado.status == ResultadoExecucao.STATUS_REVOKED


@pytest.mark.django_db
def test_revoke_without_task_id(resultado):
    resultado.task_id = None
    resultado.save()
    with mock.patch('beat.models.app.control.revoke') as mock_revoke:
        result = resultado.revoke()
        mock_revoke.assert_not_called()
    assert result is True
    resultado.refresh_from_db()
    assert resultado.status == ResultadoExecucao.STATUS_REVOKED
