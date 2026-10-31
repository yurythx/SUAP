from .tasks import get_sync_task_name


def load_tasks_schedule():
    from django_celery_beat.models import IntervalSchedule, PeriodicTask

    every_2_minutes, _ = IntervalSchedule.objects.get_or_create(
        every=2,
        period=IntervalSchedule.MINUTES,
    )

    PeriodicTask.objects.update_or_create(
        task='labfisico.tasks.sync_labs_guacamole',
        name=get_sync_task_name(),
        defaults={
            'queue': 'beat',
            'interval': every_2_minutes,
            'expire_seconds': 60,  # If not run within 60 seconds, forget it; another one will be scheduled soon.
        },
    )
