"""Beat Scheduler Implementation."""

import math

import pytz
from celery import schedules
from celery.utils.time import maybe_make_aware
from django.conf import settings
from django_celery_beat.schedulers import DatabaseScheduler, ModelEntry
from django_celery_beat.utils import NEVER_CHECK_TIMEOUT


class ModelEntryPlus(ModelEntry):
    def is_due(self):
        if not self.model.enabled:
            # 5 second delay for re-enable.
            return schedules.schedstate(False, 5.0)

        # START DATE: only run after the `start_time`, if one exists.
        if self.model.start_time is not None:
            now = self._default_now()
            if getattr(settings, 'DJANGO_CELERY_BEAT_TZ_AWARE', True):
                now = maybe_make_aware(self._default_now())
            if now < self.model.start_time:
                # The datetime is before the start date - don't run.
                # send a delay to retry on start_time
                current_tz = now.tzinfo
                start_time = self.model.due_start_time(current_tz)
                time_remaining = start_time - now
                delay = math.ceil(time_remaining.total_seconds())

                return schedules.schedstate(False, delay)

        # EXPIRED TASK: Disable task when expired
        if self.model.expires is not None:
            now = self._default_now()
            if now >= self.model.expires:
                self._disable(self.model)
                # Don't recheck
                return schedules.schedstate(False, NEVER_CHECK_TIMEOUT)

        # ONE OFF TASK: Disable one off tasks after they've ran once
        if self.model.one_off and self.model.enabled and self.model.total_run_count > 0:
            self.model.enabled = False
            self.model.total_run_count = 0  # Reset
            self.model.no_changes = False  # Mark the model entry as changed
            self.model.save()
            # Don't recheck
            return schedules.schedstate(False, NEVER_CHECK_TIMEOUT)

        # When Django settings USE_TZ is False and Django settings TIME_ZONE is set
        # value of TIME_ZINE is the time zone in which Django will store all datetimes.
        # Because of that if datetime is naive we should use it as source timezone
        # celery.utils.time.maybe_make_aware - always convert naive datetime to UTC
        # which may be wrong in Django sicase.
        django_timezone = getattr(settings, 'TIME_ZONE', None)
        django_use_tz = getattr(settings, 'USE_TZ', None)
        if not django_use_tz and django_timezone and self.last_run_at.tzinfo is None and self.app.timezone:
            source_timezone = pytz.timezone(django_timezone)
            last_run_at_django_tz = source_timezone.localize(self.last_run_at)
            self.last_run_at = last_run_at_django_tz.astimezone(self.app.timezone)

        # CAUTION: make_aware assumes settings.TIME_ZONE for naive datetimes,
        # while maybe_make_aware assumes utc for naive datetimes
        tz = self.app.timezone
        last_run_at_in_tz = maybe_make_aware(self.last_run_at).astimezone(tz)

        return self.schedule.is_due(last_run_at_in_tz)


class DatabaseSchedulerPlus(DatabaseScheduler):
    Entry = ModelEntryPlus
