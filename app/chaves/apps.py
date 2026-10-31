from djtools.apps import SuapAppConfig as AppConfig


class ChavesConfig(AppConfig):
    default = True
    name = 'chaves'
    verbose_name = 'Chaves'
    description = 'Gerencia o empréstimo/devolução de chaves na instituição.'
    icon = 'key'
    area = 'Administração'
