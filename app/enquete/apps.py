from djtools.apps import SuapAppConfig as AppConfig


class EnqueteConfig(AppConfig):
    default = True
    name = 'enquete'
    verbose_name = 'Enquetes'
    description = 'Gerencia enquetes.'
    icon = 'question-circle'
    area = 'Comunicação Social'
