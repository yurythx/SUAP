"""Tests for beat.tasks signal handlers — pre_publish_hook, pre_run_hook."""

from unittest import mock

import pytest

from beat.models import ResultadoExecucao
from beat.tasks import pre_publish_hook, pre_run_hook


@pytest.mark.django_db
class PrePublishHookTest:
    """Test pre_publish_hook signal handler."""

    def test_creates_resultado_for_call_command(self):
        """Creates ResultadoExecucao with PENDING for call_command task."""
        body = [['limpar_resultado_execucao'], {'days': 30}]
        pre_publish_hook(sender='beat.tasks.call_command', headers={}, body=body)
        resultado = ResultadoExecucao.objects.filter(
            command_name='limpar_resultado_execucao',
        ).first()
        assert resultado is not None
        assert resultado.status == ResultadoExecucao.STATUS_PENDING
        assert 'days' in resultado.kwargs
        assert resultado.args == '[]'

    def test_creates_resultado_for_execute_bash_script(self):
        """Creates ResultadoExecucao with PENDING for execute_bash_script task."""
        body = [['/usr/local/bin/backup.sh'], {}]
        pre_publish_hook(sender='beat.tasks.execute_bash_script', headers={}, body=body)
        resultado = ResultadoExecucao.objects.filter(
            command_name='/usr/local/bin/backup.sh',
        ).first()
        assert resultado is not None
        assert resultado.status == ResultadoExecucao.STATUS_PENDING
        assert body[1].get('_resultado_execucao_id') == resultado.id

    def test_ignores_other_tasks(self):
        """No ResultadoExecucao created for unknown task names."""
        body = [['some_arg'], {}]
        pre_publish_hook(sender='some.other.task', headers={}, body=body)
        assert ResultadoExecucao.objects.count() == 0


@pytest.mark.django_db
class PreRunHookTest:
    """Test pre_run_hook signal handler."""

    def test_updates_task_id(self):
        """Updates task_id on existing ResultadoExecucao."""
        resultado = ResultadoExecucao.objects.create(
            command_name='test_cmd',
            status=ResultadoExecucao.STATUS_PENDING,
        )
        task = mock.MagicMock()
        task.name = 'beat.tasks.call_command'
        pre_run_hook(
            task_id='celery-task-123',
            task=task,
            args=['test_cmd'],
            kwargs={'_resultado_execucao_id': resultado.id},
        )
        resultado.refresh_from_db()
        assert resultado.task_id == 'celery-task-123'

    def test_ignores_other_tasks(self):
        """Does not update task_id for unknown task names."""
        resultado = ResultadoExecucao.objects.create(
            command_name='test_cmd',
            status=ResultadoExecucao.STATUS_PENDING,
        )
        task = mock.MagicMock()
        task.name = 'some.other.task'
        pre_run_hook(
            task_id='celery-task-456',
            task=task,
            args=['test_cmd'],
            kwargs={'_resultado_execucao_id': resultado.id},
        )
        resultado.refresh_from_db()
        assert resultado.task_id is None

    def test_ignores_missing_resultado_id(self):
        """Does nothing when _resultado_execucao_id is not in kwargs."""
        task = mock.MagicMock()
        task.name = 'beat.tasks.call_command'
        # Should not raise
        pre_run_hook(
            task_id='celery-task-789',
            task=task,
            args=['test_cmd'],
            kwargs={},
        )

    def test_ignores_nonexistent_resultado(self):
        """Does nothing when _resultado_execucao_id points to non-existent record."""
        task = mock.MagicMock()
        task.name = 'beat.tasks.call_command'
        # Should not raise
        pre_run_hook(
            task_id='celery-task-789',
            task=task,
            args=['test_cmd'],
            kwargs={'_resultado_execucao_id': 99999},
        )
