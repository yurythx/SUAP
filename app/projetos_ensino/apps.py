from djtools.apps import SuapAppConfig as AppConfig


class ProjetosEnsinoConfig(AppConfig):
    default = True
    name = 'projetos_ensino'
    verbose_name = 'Projetos de Ensino'
    description = 'Gerencia os projetos de ensino.'
    area = 'Ensino'
