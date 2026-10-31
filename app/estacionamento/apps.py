from djtools.apps import SuapAppConfig as AppConfig


class EstacionamentoConfig(AppConfig):
    default = True
    name = 'estacionamento'
    verbose_name = 'Estacionamento'
    description = 'Controla o estacionamento.'
    icon = 'parking'
    area = 'Administração'
