import re

from django.apps import apps
from django.conf import settings

from .tasks import get_sync_task_name


def labfisico_esta_instalada():
    return 'labfisico' in settings.INSTALLED_APPS


def has_beat():
    return 'django_celery_beat' in settings.INSTALLED_APPS


def has_periodic_task():
    try:
        _ = apps.get_model(app_label='django_celery_beat', model_name='PeriodicTask')
        return True
    except LookupError:
        return False


def support_periodic_tasks():
    return has_beat() and has_periodic_task()


def is_schedule_installed():
    try:
        from django_celery_beat.models import PeriodicTask

        exists = PeriodicTask.objects.filter(name=get_sync_task_name()).exists()
        return exists
    except Exception:
        return None


def camel_case_split(identifier):
    matches = re.finditer('.+?(?:(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|$)', identifier)
    return [m.group(0) for m in matches if m.group(0).lower()]


def build_lab_name(name):
    name = re.sub(r'^(?!laboratorio)(lab[_|-]*)', '', name, flags=re.IGNORECASE)
    name.replace(' ', '_')
    name.replace('-', '_')
    return name
