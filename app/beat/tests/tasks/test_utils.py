"""Tests for beat.utils — carregar_call_command, carregar_bash_script."""

import json

import pytest

from beat.models import Agendamento
from beat.utils import carregar_bash_script, carregar_call_command


@pytest.mark.django_db
class CarregarCallCommandTest:
    """Test carregar_call_command utility function."""

    def test_with_crontab(self):
        """Creates Agendamento with crontab schedule and beat.tasks.call_command task."""
        carregar_call_command(
            'Test Task',
            'my_command',
            crontab={'minute': 30, 'hour': 14},
        )
        agendamento = Agendamento.objects.filter(name='Test Task').first()
        assert agendamento is not None
        assert agendamento.task == 'beat.tasks.call_command'
        assert agendamento.queue == 'beat'
        assert agendamento.crontab is not None
        assert agendamento.crontab.minute == '30'
        assert agendamento.crontab.hour == '14'
        assert json.loads(agendamento.args) == ['my_command']
        assert json.loads(agendamento.kwargs) == {}

    def test_with_interval(self):
        """Creates Agendamento with interval schedule."""
        carregar_call_command(
            'Interval Task',
            'my_command',
            interval=(1, 'hours'),
        )
        agendamento = Agendamento.objects.filter(name='Interval Task').first()
        assert agendamento is not None
        assert agendamento.task == 'beat.tasks.call_command'
        assert agendamento.queue == 'beat'
        assert agendamento.interval is not None
        assert agendamento.interval.every == 1
        assert agendamento.interval.period == 'hours'

    def test_without_schedule_raises_value_error(self):
        """Raises ValueError when neither interval nor crontab is provided."""
        with pytest.raises(ValueError, match='intervalo ou uma crontab'):
            carregar_call_command('No Schedule', 'my_command')

    def test_existing_task_no_duplicate(self):
        """Calling twice with the same name does not create a duplicate."""
        carregar_call_command(
            'Unique Task',
            'my_command',
            crontab={'minute': 0, 'hour': 10},
        )
        carregar_call_command(
            'Unique Task',
            'my_command',
            crontab={'minute': 0, 'hour': 10},
        )
        assert Agendamento.objects.filter(name='Unique Task').count() == 1

    def test_with_args_and_kwargs(self):
        """Args and kwargs are JSON-serialized in Agendamento."""
        carregar_call_command(
            'Args Task',
            'my_command',
            args=['--verbose', '--format=json'],
            kwargs={'days': 30, 'force': True},
            crontab={'minute': 0, 'hour': 10},
        )
        agendamento = Agendamento.objects.filter(name='Args Task').first()
        assert agendamento is not None
        assert json.loads(agendamento.args) == ['my_command', '--verbose', '--format=json']
        assert json.loads(agendamento.kwargs) == {'days': 30, 'force': True}

    def test_with_expire_seconds(self):
        """Expire seconds is stored on the Agendamento."""
        carregar_call_command(
            'Expire Task',
            'my_command',
            crontab={'minute': 0, 'hour': 10},
            expire_seconds=3600,
        )
        agendamento = Agendamento.objects.filter(name='Expire Task').first()
        assert agendamento is not None
        assert agendamento.expire_seconds == 3600


@pytest.mark.django_db
class CarregarBashScriptTest:
    """Test carregar_bash_script utility function."""

    def test_with_crontab(self):
        """Creates Agendamento with execute_bash_script task and crontab."""
        carregar_bash_script(
            'Bash Task',
            '/usr/local/bin/script.sh',
            crontab={'minute': 0, 'hour': 2},
        )
        agendamento = Agendamento.objects.filter(name='Bash Task').first()
        assert agendamento is not None
        assert agendamento.task == 'beat.tasks.execute_bash_script'
        assert agendamento.queue == 'beat'
        assert agendamento.crontab is not None
        assert agendamento.crontab.minute == '0'
        assert agendamento.crontab.hour == '2'
        assert json.loads(agendamento.args) == ['/usr/local/bin/script.sh']
        assert json.loads(agendamento.kwargs) == {}

    def test_with_interval(self):
        """Creates Agendamento with interval schedule."""
        carregar_bash_script(
            'Bash Interval',
            '/usr/local/bin/script.sh',
            interval=(30, 'minutes'),
        )
        agendamento = Agendamento.objects.filter(name='Bash Interval').first()
        assert agendamento is not None
        assert agendamento.task == 'beat.tasks.execute_bash_script'
        assert agendamento.interval is not None
        assert agendamento.interval.every == 30
        assert agendamento.interval.period == 'minutes'

    def test_without_schedule_raises_value_error(self):
        """Raises ValueError when neither interval nor crontab is provided."""
        with pytest.raises(ValueError, match='intervalo ou uma crontab'):
            carregar_bash_script('No Schedule', '/usr/local/bin/script.sh')

    def test_with_args(self):
        """Args are JSON-serialized in Agendamento."""
        carregar_bash_script(
            'Bash With Args',
            '/usr/local/bin/script.sh',
            args=['--dry-run'],
            crontab={'minute': 0, 'hour': 3},
        )
        agendamento = Agendamento.objects.filter(name='Bash With Args').first()
        assert agendamento is not None
        assert json.loads(agendamento.args) == ['/usr/local/bin/script.sh', '--dry-run']
