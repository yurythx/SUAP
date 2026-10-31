from djtools.apps import SuapAppConfig as AppConfig


class ConveniosConfig(AppConfig):
    default = True
    name = 'convenios'
    verbose_name = 'Convênios'
    description = 'Gerencia os convênios da instituição.'
    icon = 'comment-dollar'
    area = 'Extensão'
