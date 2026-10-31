from djtools.apps import SuapAppConfig as AppConfig


class EgressosConfig(AppConfig):
    default = True
    name = 'egressos'
    verbose_name = 'Egressos'
    description = 'Gerencia os egressos da instituição.'
    icon = 'external-link-square-alt'
    area = 'Extensão'
