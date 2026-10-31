# ruff: noqa: F401

from djtools.apps import SuapAppConfig as AppConfig


class BeatConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    default = True
    name = 'beat'
    verbose_name = 'Agendamento de Tarefas'
    description = 'Agendamento de Tarefas no SUAP.'
    icon = 'schedule'
    area = 'Tecnologia da Informação'

    def ready(self):
        import beat.tasks
