from djtools.apps import SuapAppConfig as AppConfig


class ProjetosConfig(AppConfig):
    default = True
    name = 'projetos'
    verbose_name = 'Projetos'
    description = 'Gerencia os projetos de extensão.'
    icon = 'briefcase'
    area = 'Extensão'
