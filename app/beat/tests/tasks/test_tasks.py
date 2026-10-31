"""Tests for beat.tasks — call_command, execute_bash_script, run_command_with_capture."""

import subprocess
from unittest import mock

import pytest
from celery.exceptions import SoftTimeLimitExceeded

from beat.models import ResultadoExecucao
from beat.tasks import (
    call_command,
    execute_bash_script,
    run_command_with_capture,
)


@pytest.mark.django_db
class CallCommandTaskTest:
    """Test beat.tasks.call_command Celery task."""

    def test_success(self):
        """Successful command execution sets STATUS_SUCCESS and stores output."""
        with mock.patch('beat.tasks.run_command_with_capture') as mock_run:
            mock_run.return_value = ('stdout output', 'stderr error')
            result_msg = call_command('test_command')
        assert result_msg == "Comando 'test_command' executado com sucesso."
        resultado = ResultadoExecucao.objects.filter(command_name='test_command').first()
        assert resultado is not None
        assert resultado.status == ResultadoExecucao.STATUS_SUCCESS
        assert resultado.stdout == 'stdout output'
        assert resultado.stderr == 'stderr error'
        assert resultado.datetime_end is not None

    def test_called_process_error(self):
        """CalledProcessError from subprocess sets STATUS_FAILED."""
        proc_error = subprocess.CalledProcessError(
            returncode=1,
            cmd='test_command',
            output='error out',
            stderr='error err',
        )
        with mock.patch('beat.tasks.run_command_with_capture') as mock_run:
            mock_run.side_effect = proc_error
            with pytest.raises(subprocess.CalledProcessError):
                call_command('test_command')
        resultado = ResultadoExecucao.objects.filter(command_name='test_command').first()
        assert resultado is not None
        assert resultado.status == ResultadoExecucao.STATUS_FAILED
        assert resultado.datetime_end is not None

    def test_timeout_expired(self):
        """TimeoutExpired from subprocess sets STATUS_TIMEOUT."""
        timeout_error = subprocess.TimeoutExpired(
            cmd='test_command',
            timeout=30,
            output='partial out',
            stderr='partial err',
        )
        with mock.patch('beat.tasks.run_command_with_capture') as mock_run:
            mock_run.side_effect = timeout_error
            with pytest.raises(subprocess.TimeoutExpired):
                call_command('test_command')
        resultado = ResultadoExecucao.objects.filter(command_name='test_command').first()
        assert resultado is not None
        assert resultado.status == ResultadoExecucao.STATUS_TIMEOUT
        assert resultado.datetime_end is not None

    def test_soft_time_limit(self):
        """SoftTimeLimitExceeded sets STATUS_TIMEOUT on new result."""
        with mock.patch('beat.tasks.run_command_with_capture') as mock_run:
            mock_run.side_effect = SoftTimeLimitExceeded()
            with pytest.raises(SoftTimeLimitExceeded):
                call_command('test_command')
        resultado = ResultadoExecucao.objects.filter(command_name='test_command').first()
        assert resultado is not None
        assert resultado.status == ResultadoExecucao.STATUS_TIMEOUT
        assert resultado.datetime_end is not None

    def test_generic_exception(self):
        """Generic exception sets STATUS_FAILED on new result."""
        with mock.patch('beat.tasks.run_command_with_capture') as mock_run:
            mock_run.side_effect = ValueError('generic error')
            with pytest.raises(ValueError, match='generic error'):
                call_command('test_gen_err')
        resultado = ResultadoExecucao.objects.filter(command_name='test_gen_err').first()
        assert resultado is not None
        assert resultado.status == ResultadoExecucao.STATUS_FAILED
        assert resultado.datetime_end is not None

    def test_invalid_timeout_negative(self):
        """Negative timeout raises ValueError and sets STATUS_FAILED."""
        with mock.patch('beat.tasks.run_command_with_capture') as mock_run:
            with pytest.raises(ValueError, match='inválido'):
                call_command('test_command', timeout=-1)
            mock_run.assert_not_called()
        resultado = ResultadoExecucao.objects.filter(command_name='test_command').first()
        assert resultado is not None
        assert resultado.status == ResultadoExecucao.STATUS_FAILED
        assert resultado.datetime_end is not None
        assert 'inválido' in (resultado.stderr or '')

    def test_invalid_timeout_non_numeric(self):
        """Non-numeric timeout raises ValueError and sets STATUS_FAILED."""
        with mock.patch('beat.tasks.run_command_with_capture') as mock_run:
            with pytest.raises(ValueError, match='inválido'):
                call_command('test_command', timeout='abc')
            mock_run.assert_not_called()
        resultado = ResultadoExecucao.objects.filter(command_name='test_command').first()
        assert resultado is not None
        assert resultado.status == ResultadoExecucao.STATUS_FAILED
        assert resultado.datetime_end is not None

    def test_existing_resultado_execucao(self):
        """Passing _resultado_execucao_id updates existing record on success."""
        resultado = ResultadoExecucao.objects.create(
            command_name='test_existing',
            args='()',
            kwargs='{}',
            status=ResultadoExecucao.STATUS_RUNNING,
        )
        with mock.patch('beat.tasks.run_command_with_capture') as mock_run:
            mock_run.return_value = ('stdout', 'stderr')
            call_command('test_existing', _resultado_execucao_id=resultado.id)
        resultado.refresh_from_db()
        assert resultado.status == ResultadoExecucao.STATUS_SUCCESS
        assert resultado.stdout == 'stdout'
        assert resultado.stderr == 'stderr'
        assert resultado.datetime_end is not None

    def test_existing_resultado_execucao_soft_timeout(self):
        """Existing result with SoftTimeLimitExceeded gets STATUS_TIMEOUT."""
        resultado = ResultadoExecucao.objects.create(
            command_name='test_existing',
            args='()',
            kwargs='{}',
            status=ResultadoExecucao.STATUS_RUNNING,
        )
        with mock.patch('beat.tasks.run_command_with_capture') as mock_run:
            mock_run.side_effect = SoftTimeLimitExceeded()
            with pytest.raises(SoftTimeLimitExceeded):
                call_command('test_existing', _resultado_execucao_id=resultado.id)
        resultado.refresh_from_db()
        assert resultado.status == ResultadoExecucao.STATUS_TIMEOUT
        assert resultado.datetime_end is not None

    def test_no_resultado_execucao_id(self):
        """Passing a non-existent _resultado_execucao_id creates a new record."""
        with mock.patch('beat.tasks.run_command_with_capture') as mock_run:
            mock_run.return_value = ('output', 'error')
            call_command('test_new', _resultado_execucao_id=99999)
        # A new result should be created since 99999 doesn't exist
        resultados = ResultadoExecucao.objects.filter(command_name='test_new')
        assert resultados.count() == 1
        assert resultados.first().status == ResultadoExecucao.STATUS_SUCCESS


@pytest.mark.django_db
class ExecuteBashScriptTaskTest:
    """Test beat.tasks.execute_bash_script Celery task."""

    def _mock_subprocess_run(self, stdout='', stderr='', returncode=0):
        """Helper to create a mock subprocess.CompletedProcess."""
        proc = mock.MagicMock()
        proc.stdout = stdout
        proc.stderr = stderr
        proc.returncode = returncode
        return proc

    def test_success(self):
        """Successful script execution sets STATUS_SUCCESS."""
        with mock.patch('beat.tasks.subprocess.run') as mock_run:
            mock_run.return_value = self._mock_subprocess_run(
                stdout='script output',
                stderr='',
            )
            result_msg = execute_bash_script('/usr/local/bin/test.sh')
        assert "Script '/usr/local/bin/test.sh' executado com sucesso" in result_msg
        resultado = ResultadoExecucao.objects.filter(command_name='/usr/local/bin/test.sh').first()
        assert resultado is not None
        assert resultado.status == ResultadoExecucao.STATUS_SUCCESS
        assert resultado.stdout == 'script output'
        assert resultado.datetime_end is not None

    def test_file_not_found(self):
        """FileNotFoundError sets STATUS_FAILED."""
        with mock.patch('beat.tasks.subprocess.run') as mock_run:
            mock_run.side_effect = FileNotFoundError()
            with pytest.raises(FileNotFoundError):
                execute_bash_script('/nonexistent/script.sh')
        resultado = ResultadoExecucao.objects.filter(command_name='/nonexistent/script.sh').first()
        assert resultado is not None
        assert resultado.status == ResultadoExecucao.STATUS_FAILED
        assert resultado.datetime_end is not None

    def test_called_process_error(self):
        """CalledProcessError sets STATUS_FAILED."""
        proc_error = subprocess.CalledProcessError(
            returncode=1,
            cmd='/usr/local/bin/test.sh',
            output='stdout',
            stderr='stderr',
        )
        with mock.patch('beat.tasks.subprocess.run') as mock_run:
            mock_run.side_effect = proc_error
            with pytest.raises(subprocess.CalledProcessError):
                execute_bash_script('/usr/local/bin/test.sh')
        resultado = ResultadoExecucao.objects.filter(command_name='/usr/local/bin/test.sh').first()
        assert resultado is not None
        assert resultado.status == ResultadoExecucao.STATUS_FAILED
        assert resultado.datetime_end is not None

    def test_timeout_expired(self):
        """TimeoutExpired sets STATUS_TIMEOUT."""
        timeout_error = subprocess.TimeoutExpired(
            cmd='/usr/local/bin/test.sh',
            timeout=10,
            output='partial',
            stderr='',
        )
        with mock.patch('beat.tasks.subprocess.run') as mock_run:
            mock_run.side_effect = timeout_error
            with pytest.raises(subprocess.TimeoutExpired):
                execute_bash_script('/usr/local/bin/test.sh')
        resultado = ResultadoExecucao.objects.filter(command_name='/usr/local/bin/test.sh').first()
        assert resultado is not None
        assert resultado.status == ResultadoExecucao.STATUS_TIMEOUT
        assert resultado.datetime_end is not None

    def test_invalid_timeout_negative(self):
        """Negative timeout raises ValueError and sets STATUS_FAILED."""
        with mock.patch('beat.tasks.subprocess.run') as mock_run:
            with pytest.raises(ValueError, match='inválido'):
                execute_bash_script('/usr/local/bin/test.sh', timeout=-1)
            mock_run.assert_not_called()
        resultado = ResultadoExecucao.objects.filter(command_name='/usr/local/bin/test.sh').first()
        assert resultado is not None
        assert resultado.status == ResultadoExecucao.STATUS_FAILED
        assert resultado.datetime_end is not None

    def test_invalid_timeout_non_numeric(self):
        """Non-numeric timeout raises ValueError and sets STATUS_FAILED."""
        with mock.patch('beat.tasks.subprocess.run') as mock_run:
            with pytest.raises(ValueError, match='inválido'):
                execute_bash_script('/usr/local/bin/test.sh', timeout='abc')
            mock_run.assert_not_called()
        resultado = ResultadoExecucao.objects.filter(command_name='/usr/local/bin/test.sh').first()
        assert resultado is not None
        assert resultado.status == ResultadoExecucao.STATUS_FAILED
        assert resultado.datetime_end is not None

    def test_existing_resultado_execucao(self):
        """Passing _resultado_execucao_id updates existing record."""
        resultado = ResultadoExecucao.objects.create(
            command_name='/usr/local/bin/test.sh',
            args='()',
            kwargs='{}',
            status=ResultadoExecucao.STATUS_RUNNING,
        )
        with mock.patch('beat.tasks.subprocess.run') as mock_run:
            mock_run.return_value = self._mock_subprocess_run(stdout='output')
            execute_bash_script('/usr/local/bin/test.sh', _resultado_execucao_id=resultado.id)
        resultado.refresh_from_db()
        assert resultado.status == ResultadoExecucao.STATUS_SUCCESS
        assert resultado.stdout == 'output'
        assert resultado.datetime_end is not None

    def test_no_resultado_execucao_id(self):
        """Passing a non-existent _resultado_execucao_id creates a new record."""
        with mock.patch('beat.tasks.subprocess.run') as mock_run:
            mock_run.return_value = self._mock_subprocess_run(stdout='output')
            execute_bash_script('/usr/local/bin/test.sh', _resultado_execucao_id=99999)
        resultados = ResultadoExecucao.objects.filter(command_name='/usr/local/bin/test.sh')
        assert resultados.count() == 1
        assert resultados.first().status == ResultadoExecucao.STATUS_SUCCESS


class RunCommandWithCaptureTest:
    """Test run_command_with_capture utility function."""

    def test_success(self):
        """Returns (stdout, stderr) from subprocess.run."""
        proc = mock.MagicMock()
        proc.stdout = 'stdout result'
        proc.stderr = 'stderr result'
        proc.returncode = 0
        with mock.patch('beat.tasks.subprocess.run', return_value=proc) as mock_run:
            stdout, stderr = run_command_with_capture('test_cmd')
        assert stdout == 'stdout result'
        assert stderr == 'stderr result'
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        assert args[0] == ['python', 'manage.py', 'test_cmd']
        assert kwargs['capture_output'] is True
        assert kwargs['text'] is True
        assert kwargs['check'] is True
        assert kwargs['timeout'] is None

    def test_with_args_and_kwargs(self):
        """Positional and keyword arguments are formatted as CLI flags."""
        proc = mock.MagicMock()
        proc.stdout = ''
        proc.stderr = ''
        with mock.patch('beat.tasks.subprocess.run', return_value=proc) as mock_run:
            run_command_with_capture('test_cmd', 'arg1', 'arg2', key='value', v=True)
        args, _ = mock_run.call_args
        command = args[0]
        assert command == ['python', 'manage.py', 'test_cmd', 'arg1', 'arg2', '--key=value', '-v']

    def test_timeout_passed(self):
        """Timeout parameter is forwarded to subprocess.run."""
        proc = mock.MagicMock()
        proc.stdout = ''
        proc.stderr = ''
        with mock.patch('beat.tasks.subprocess.run', return_value=proc) as mock_run:
            run_command_with_capture('test_cmd', timeout=60)
        _, kwargs = mock_run.call_args
        assert kwargs['timeout'] == 60

    def test_failure_raises(self):
        """CalledProcessError from subprocess.run propagates."""
        error = subprocess.CalledProcessError(
            returncode=1,
            cmd='python manage.py test_cmd',
            output='',
            stderr='error',
        )
        with mock.patch('beat.tasks.subprocess.run', side_effect=error), pytest.raises(subprocess.CalledProcessError):
            run_command_with_capture('test_cmd')
