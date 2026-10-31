"""Tests for beat.schedulers — ModelEntryPlus.is_due edge cases."""

import datetime
from unittest import mock

import pytest
from celery import schedules

from beat.models import Agendamento, Intervalo
from beat.schedulers import ModelEntryPlus


@pytest.mark.django_db
class ModelEntryPlusIsDueTest:
    """Test ModelEntryPlus.is_due edge cases."""

    def setup_method(self):
        self.interval = Intervalo.objects.create(every=1, period='hours')
        self.periodic_task = Agendamento.objects.create(
            name='test_scheduler_task',
            task='beat.tasks.call_command',
            enabled=True,
            interval=self.interval,
        )

    def _make_entry(self):
        """Create a ModelEntryPlus instance with a mock app."""
        import pytz

        mock_app = mock.MagicMock()
        mock_app.timezone = pytz.UTC
        return ModelEntryPlus(self.periodic_task, app=mock_app)

    def test_disabled_model(self):
        """Disabled task returns (False, 5.0)."""
        self.periodic_task.enabled = False
        self.periodic_task.save()
        entry = self._make_entry()
        state = entry.is_due()
        assert state.is_due is False
        assert state.next == 5.0

    def test_start_time_in_future(self):
        """Task with start_time in the future returns (False, delay)."""
        import pytz

        now_aware = datetime.datetime.now(pytz.UTC)
        future_aware = now_aware + datetime.timedelta(hours=2)
        self.periodic_task.start_time = future_aware
        self.periodic_task.save()
        entry = self._make_entry()

        with mock.patch.object(entry, '_default_now', return_value=now_aware):
            state = entry.is_due()

        assert state.is_due is False
        assert state.next > 0

    def test_expired_task(self):
        """Expired task returns (False, NEVER_CHECK_TIMEOUT) and disables itself."""
        import pytz

        now_aware = datetime.datetime.now(pytz.UTC)
        past_aware = now_aware - datetime.timedelta(hours=1)
        self.periodic_task.expires = past_aware
        self.periodic_task.save()
        entry = self._make_entry()

        with mock.patch.object(entry, '_default_now', return_value=now_aware), mock.patch.object(entry, '_disable') as mock_disable:
            state = entry.is_due()

        assert state.is_due is False
        assert state.next == 100000000  # NEVER_CHECK_TIMEOUT
        mock_disable.assert_called_once_with(self.periodic_task)

    def test_one_off_already_run(self):
        """One-off task that already ran returns (False, NEVER_CHECK_TIMEOUT) and disables."""
        self.periodic_task.one_off = True
        self.periodic_task.total_run_count = 1
        self.periodic_task.save()
        entry = self._make_entry()

        state = entry.is_due()

        assert state.is_due is False
        assert state.next == 100000000  # NEVER_CHECK_TIMEOUT
        self.periodic_task.refresh_from_db()
        assert self.periodic_task.enabled is False

    def test_normal_due_check(self):
        """Enabled task with no constraints delegates to schedule.is_due."""
        import pytz

        now_aware = datetime.datetime.now(pytz.UTC)
        entry = self._make_entry()

        with mock.patch.object(entry, '_default_now', return_value=now_aware):
            entry.last_run_at = now_aware - datetime.timedelta(hours=2)
            entry.schedule = mock.MagicMock()
            expected_state = schedules.schedstate(True, 0.0)
            entry.schedule.is_due.return_value = expected_state

            state = entry.is_due()

        assert state == expected_state
        entry.schedule.is_due.assert_called_once()
