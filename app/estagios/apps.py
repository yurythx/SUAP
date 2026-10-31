# ruff: noqa: F401
from djtools.apps import SuapAppConfig as AppConfig


class EstagiosConfig(AppConfig):
    default = True
    name = 'estagios'
    verbose_name = 'Estágios'
    description = 'Gerencia os estágios, aprendizagens e atividades profissionais efetivas.'
    icon = 'briefcase'
    area = 'Extensão'

    def ready(self):
        import estagios.signals  # registrando os signals
