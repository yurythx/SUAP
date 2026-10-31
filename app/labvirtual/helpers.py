from django.apps import apps
from django.conf import settings

from comum.models import Vinculo

from .tasks import get_sync_task_name


class DictObj:
    def __init__(self, in_dict: dict):
        assert isinstance(in_dict, dict)
        for key, val in in_dict.items():
            if isinstance(val, list | tuple):
                setattr(self, key, [DictObj(x) if isinstance(x, dict) else x for x in val])
            else:
                setattr(self, key, DictObj(val) if isinstance(val, dict) else val)


def extrair_vinculos_do_diario(diario):
    if diario:
        alunos = diario.get_alunos_ativos()
        ids = alunos.values_list('matricula_periodo__aluno__vinculos', flat=True)
        return Vinculo.objects.filter(id__in=ids)
    return []


def labvirtual_esta_instalada():
    return 'labvirtual' in settings.INSTALLED_APPS


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
