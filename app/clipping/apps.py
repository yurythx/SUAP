from djtools.apps import SuapAppConfig as AppConfig


class ClippingConfig(AppConfig):
    default = True
    name = 'clipping'
    verbose_name = 'Clipping'
    description = 'Gerencia notícias externas para salvamento em formato clipping.'
    icon = 'newspaper'
    area = 'Comunicação Social'
