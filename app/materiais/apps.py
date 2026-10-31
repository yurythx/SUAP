from djtools.apps import SuapAppConfig as AppConfig


class MateriaisConfig(AppConfig):
    default = True
    name = 'materiais'
    verbose_name = 'Materiais'
    description = 'Gerencia os materiais.'
    icon = 'cube'
    area = 'Administração'
