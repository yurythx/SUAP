from djtools.apps import SuapAppConfig as AppConfig


class ProgramaGestaoConfig(AppConfig):
    default = True
    name = 'pgd2'
    verbose_name = 'Programa de Gestão 2'
    area = 'Programa de Gestão'
    icon = 'people-roof'
    description = 'Módulo do Programa de Gestão 2.'
