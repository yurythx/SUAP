from djtools.apps import SuapAppConfig as AppConfig


class ComumConfig(AppConfig):
    default = True
    name = 'comum'
    verbose_name = 'Comum'
    description = 'Gerencia as configurações e cadastros gerais para uso de todos os módulos do SUAP.'
    icon = 'list'
    area = 'Comum'
