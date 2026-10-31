from djtools.apps import SuapAppConfig as AppConfig


class MicrosoftConfig(AppConfig):
    default = True
    name = 'microsoft'
    verbose_name = 'Microsoft'
    description = 'Integra os serviços da Microsoft.'
    icon = 'laptop'
    area = 'Tecnologia da Informação'
