from djtools.apps import SuapAppConfig as AppConfig


class PlanejamentoConfig(AppConfig):
    default = True
    name = 'planejamento'
    verbose_name = 'Planejamento'
    description = 'Foi substituído pelo módulo de Planejamento Estratégico, servindo agora apenas de histórico dos planejamentos anteriores.'
    icon = 'chart-pie'
    area = 'Desenvolvimento Institucional'
