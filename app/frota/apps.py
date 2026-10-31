from djtools.apps import SuapAppConfig as AppConfig


class FrotaConfig(AppConfig):
    default = True
    name = 'frota'
    verbose_name = 'Frota'
    description = 'Gerencia frota e faz o controle de viagens.'
    icon = 'car'
    area = 'Administração'
