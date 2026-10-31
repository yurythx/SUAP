from djtools.apps import SuapAppConfig as AppConfig


class SolenidadesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'solenidades'
    default = True
    verbose_name = 'Solenidades'
    description = 'Gerencia os agendamentos de solenidades.'
    area = 'Comum'
