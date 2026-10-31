from djtools.apps import SuapAppConfig as AppConfig


class PlanV2Config(AppConfig):
    default = True
    name = 'plan_v2'
    verbose_name = 'Planejamento - versão 2'
    description = 'Foi substituído pelo módulo de Planejamento Estratégico, servindo agora apenas de histórico dos planejamentos anteriores.'
    icon = 'chart-pie'
    area = 'Desenvolvimento Institucional'
