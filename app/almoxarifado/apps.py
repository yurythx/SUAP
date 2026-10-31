from djtools.apps import SuapAppConfig as AppConfig


class AlmoxarifadoConfig(AppConfig):
    default = True
    name = 'almoxarifado'
    verbose_name = 'Almoxarifado'
    description = 'Controla entradas, empenhos, materiais de consumo e estoque.'
    icon = 'store'
    area = 'Administração'
