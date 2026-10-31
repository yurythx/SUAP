from djtools.apps import SuapAppConfig as AppConfig


class PedagogiaConfig(AppConfig):
    default = True
    name = 'pedagogia'
    verbose_name = 'Pedagogia'
    description = 'Auxilia a Avaliação de Cursos.'
    icon = 'percent'
    area = 'Ensino'
