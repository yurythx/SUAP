"""Tests for beat.forms — AgendamentoForm validation and save behavior."""

import datetime

import pytest

from beat.forms import AgendamentoForm
from beat.models import Agendamento, Intervalo


@pytest.mark.django_db
class AgendamentoFormTest:
    """Test AgendamentoForm validation and save behavior."""

    def test_clean_valid_json_args(self):
        """Valid JSON args pass validation."""
        interval = Intervalo.objects.create(every=1, period='hours')
        form = AgendamentoForm(
            data={
                'name': 'Test Task',
                'regtask': 'beat.tasks.call_command',
                'task': 'beat.tasks.call_command',
                'args': '["my_command"]',
                'kwargs': '{}',
                'interval': interval.pk,
                'enabled': True,
            }
        )
        assert form.is_valid(), form.errors.as_text()

    def test_clean_invalid_json_args(self):
        """Invalid JSON args raise ValidationError."""
        interval = Intervalo.objects.create(every=1, period='hours')
        form = AgendamentoForm(
            data={
                'name': 'Test Task',
                'regtask': 'beat.tasks.call_command',
                'task': 'beat.tasks.call_command',
                'args': 'not valid json',
                'kwargs': '{}',
                'interval': interval.pk,
                'enabled': True,
            }
        )
        assert not form.is_valid()
        assert 'args' in form.errors

    def test_clean_valid_json_kwargs(self):
        """Valid JSON kwargs pass validation."""
        interval = Intervalo.objects.create(every=1, period='hours')
        form = AgendamentoForm(
            data={
                'name': 'Test Task',
                'regtask': 'beat.tasks.call_command',
                'task': 'beat.tasks.call_command',
                'args': '[]',
                'kwargs': '{"days": 30}',
                'interval': interval.pk,
                'enabled': True,
            }
        )
        assert form.is_valid(), form.errors.as_text()

    def test_clean_invalid_json_kwargs(self):
        """Invalid JSON kwargs raise ValidationError."""
        interval = Intervalo.objects.create(every=1, period='hours')
        form = AgendamentoForm(
            data={
                'name': 'Test Task',
                'regtask': 'beat.tasks.call_command',
                'task': 'beat.tasks.call_command',
                'args': '[]',
                'kwargs': '{bad json}',
                'interval': interval.pk,
                'enabled': True,
            }
        )
        assert not form.is_valid()
        assert 'kwargs' in form.errors

    def test_clean_expire_seconds_and_expires_conflict(self):
        """Setting both expire_seconds and expires raises ValidationError."""
        interval = Intervalo.objects.create(every=1, period='hours')
        agendamento = Agendamento(
            name='Test Conflict',
            task='beat.tasks.call_command',
            interval=interval,
            expire_seconds=3600,
            expires=datetime.datetime(2025, 1, 1, 0, 0, 0),
        )
        with pytest.raises(Exception) as exc_info:
            agendamento.save()
        error_msg = str(exc_info.value)
        # The message may be translated. Accept either English or Portuguese.
        assert 'Only one can be set' in error_msg or 'Apenas um pode ser definido' in error_msg

    def test_save_sets_task_and_queue(self):
        """Save sets task from regtask field and queue to 'beat'."""
        interval = Intervalo.objects.create(every=1, period='hours')
        form = AgendamentoForm(
            data={
                'name': 'Save Test',
                'regtask': 'beat.tasks.call_command',
                'task': 'beat.tasks.call_command',
                'args': '[]',
                'kwargs': '{}',
                'interval': interval.pk,
                'enabled': True,
            }
        )
        assert form.is_valid(), form.errors.as_text()
        agendamento = form.save()
        assert agendamento.task == 'beat.tasks.call_command'
        assert agendamento.queue == 'beat'
        assert agendamento.name == 'Save Test'
