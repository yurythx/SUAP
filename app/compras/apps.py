from djtools.apps import SuapAppConfig as AppConfig


class ComprasConfig(AppConfig):
    default = True
    name = 'compras'
    verbose_name = 'Compras'
    description = 'Gerencia compras.'
    icon = 'shopping-cart'
    area = 'Administração'
