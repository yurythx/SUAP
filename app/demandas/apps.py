from djtools.apps import SuapAppConfig as AppConfig


class DemandasConfig(AppConfig):
    default = True
    name = 'demandas'
    verbose_name = 'Demandas'
    description = 'Controla todo ciclo de desenvolvimento de novas funcionalidades para o SUAP  planejadas por cada área sistêmica da instituição.'
    icon = 'code'
    area = 'Tecnologia da Informação'
