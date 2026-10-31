from djtools.apps import SuapAppConfig as AppConfig


class ErrosConfig(AppConfig):
    default = True
    name = 'erros'
    verbose_name = 'Erros'
    description = 'Gerencia os erros encontrados e relatados no sistema.'
    icon = 'bug'
    area = 'Tecnologia da Informação'
