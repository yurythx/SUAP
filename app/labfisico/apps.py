# ruff: noqa: F401
from djtools.apps import SuapAppConfig as AppConfig


class LabfisicoConfig(AppConfig):
    default = True
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'labfisico'
    verbose_name = 'Laboratório Fisico'
    area = 'Ensino'
    description = 'Realiza o controle de laboratórios físicos.'
    icon = 'chalkboard-teacher'

    def ready(self):
        import labfisico.signals
