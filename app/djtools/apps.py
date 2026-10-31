# ruff: noqa: F401
from django.apps import AppConfig


class SuapAppConfig(AppConfig):
    area = ''

    def get_full_name(self):
        return f'{self.area} :: {self.verbose_name}'


class DjtoolsConfig(SuapAppConfig):
    default = True
    name = 'djtools'
    verbose_name = 'Djtools'
    description = 'Gerencia classes e funções utilitárias utilizadas para o desenvolvimento do SUAP.'
    area = 'Tecnologia da Informação'
    icon = 'tools'

    def ready(self):
        import djtools.history
        import djtools.patches
