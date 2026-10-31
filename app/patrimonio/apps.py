from djtools.apps import SuapAppConfig as AppConfig


class PatrimonioConfig(AppConfig):
    default = True
    name = 'patrimonio'
    verbose_name = 'Patrimônio'
    description = 'Gerencia o patrimônio da insituição, gerenciando transferências de carga, baixas, cautelas etc.'
    icon = 'coins'
    area = 'Administração'
