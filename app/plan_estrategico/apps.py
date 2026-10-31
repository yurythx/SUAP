from djtools.apps import SuapAppConfig as AppConfig


class PlanEstrategicoConfig(AppConfig):
    default = True
    name = 'plan_estrategico'
    verbose_name = 'Planejamento Estratégico'
    description = 'Permite o registro do plano estratégico e acompanhamento do desempenho institucional, bem como dos desdobramentos anuais do planejamento estratégico.'
    icon = 'chart-bar'
    area = 'Desenvolvimento Institucional'
