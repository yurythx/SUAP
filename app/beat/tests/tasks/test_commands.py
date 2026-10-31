"""Tests for beat management commands — limpar_resultado_execucao, importar_tarefas_celery_beat."""

import datetime
from unittest import mock

import pytest
from django.core.management import call_command as django_call_command

from beat.models import ResultadoExecucao


@pytest.mark.django_db
class LimparResultadoExecucaoCommandTest:
    """Test limpar_resultado_execucao management command."""

    def test_deletes_old_results(self):
        """Results older than the default 30 days are deleted."""
        now = datetime.datetime.now()
        old_date = now - datetime.timedelta(days=31)
        keep_date = now - datetime.timedelta(days=29)

        old_result = ResultadoExecucao.objects.create(
            command_name='old_task',
            status=ResultadoExecucao.STATUS_SUCCESS,
        )
        keep_result = ResultadoExecucao.objects.create(
            command_name='keep_task',
            status=ResultadoExecucao.STATUS_SUCCESS,
        )
        # Bypass auto_now_add to set old datetime_start
        ResultadoExecucao.objects.filter(id=old_result.id).update(datetime_start=old_date)
        ResultadoExecucao.objects.filter(id=keep_result.id).update(datetime_start=keep_date)

        django_call_command('limpar_resultado_execucao', '--days=30', verbosity=0)

        assert not ResultadoExecucao.objects.filter(id=old_result.id).exists()
        assert ResultadoExecucao.objects.filter(id=keep_result.id).exists()

    def test_finalizes_stale_running_results(self):
        """Running results older than 1 day get timeout status and datetime_end."""
        now = datetime.datetime.now()
        stale_date = now - datetime.timedelta(days=2)
        recent_date = now - datetime.timedelta(hours=12)

        stale_result = ResultadoExecucao.objects.create(
            command_name='stale_task',
            status=ResultadoExecucao.STATUS_RUNNING,
        )
        recent_result = ResultadoExecucao.objects.create(
            command_name='recent_task',
            status=ResultadoExecucao.STATUS_RUNNING,
        )
        ResultadoExecucao.objects.filter(id=stale_result.id).update(datetime_start=stale_date)
        ResultadoExecucao.objects.filter(id=recent_result.id).update(datetime_start=recent_date)

        django_call_command('limpar_resultado_execucao', '--days=30', verbosity=0)

        stale_result.refresh_from_db()
        assert stale_result.status == ResultadoExecucao.STATUS_TIMEOUT
        assert stale_result.datetime_end is not None

        recent_result.refresh_from_db()
        assert recent_result.status == ResultadoExecucao.STATUS_RUNNING
        assert recent_result.datetime_end is None

    def test_custom_days(self):
        """Custom --days parameter changes the deletion threshold."""
        now = datetime.datetime.now()
        twenty_days_ago = now - datetime.timedelta(days=20)

        old_result = ResultadoExecucao.objects.create(
            command_name='custom_old',
            status=ResultadoExecucao.STATUS_SUCCESS,
        )
        ResultadoExecucao.objects.filter(id=old_result.id).update(datetime_start=twenty_days_ago)

        django_call_command('limpar_resultado_execucao', '--days=18', verbosity=0)

        assert not ResultadoExecucao.objects.filter(id=old_result.id).exists()


@pytest.mark.django_db
class ImportarTarefasCommandTest:
    """Test importar_tarefas_celery_beat management command."""

    def test_loads_beat_tasks(self):
        """Imports beat.py modules from installed apps and calls load_tasks_schedule."""
        mock_beat_module = mock.MagicMock()
        mock_exists = mock.MagicMock(return_value=True)

        with mock.patch('os.path.exists', mock_exists), mock.patch('importlib.import_module', return_value=mock_beat_module) as mock_import:
            django_call_command('importar_tarefas_celery_beat', verbosity=0)

        # Verify importlib.import_module was called for at least one app
        mock_import.assert_any_call(mock.ANY)
        # Verify load_tasks_schedule was called on the imported module
        assert mock_beat_module.load_tasks_schedule.called
