# ruff: noqa: F401
from djtools.apps import SuapAppConfig as AppConfig


class LabvirtualConfig(AppConfig):
    default = True
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'labvirtual'
    verbose_name = 'Laboratório Virtual'
    area = 'Ensino'
    description = 'Realiza o controle de laboratórios virtuais.'
    icon = 'chalkboard-teacher'

    def ready(self):
        import labvirtual.signals
