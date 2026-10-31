from djtools.apps import SuapAppConfig as AppConfig


class ProgramaGestaoConfig(AppConfig):
    default = True
    name = 'pgd'
    verbose_name = 'Programa de Gestão'
    area = 'Programa de Gestão'
    icon = 'people-roof'
    description = 'Módulo do Programa de Gestão.'
