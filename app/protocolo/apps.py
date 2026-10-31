from djtools.apps import SuapAppConfig as AppConfig


class ProtocoloConfig(AppConfig):
    default = True
    name = 'protocolo'
    verbose_name = 'Protocolo'
    description = 'Gerencia os Procesos Físicos.'
    area = 'Administração'
    icon = 'folder-open'
