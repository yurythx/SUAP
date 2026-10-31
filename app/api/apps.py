# ruff: noqa: F401

from djtools.apps import SuapAppConfig as AppConfig


class ApiConfig(AppConfig):
    default = True
    name = 'api'
    verbose_name = 'API'
    description = 'Realiza o cadastro das aplicações que irão poder consumir os endpoints do SUAP.'
    icon = 'tablet'
    area = 'Tecnologia da Informação'

    def ready(self):
        # Assegurar que todos os signal handlers estejam conectados
        from . import handlers
