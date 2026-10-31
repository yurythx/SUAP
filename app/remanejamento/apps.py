from djtools.apps import SuapAppConfig as AppConfig


class RemanejamentoConfig(AppConfig):
    default = True
    name = 'remanejamento'
    verbose_name = 'Remoção Interna'
    description = 'Gerencia os dados e fluxos do processo de concorrência aos editais de Remoção Interna de servidores.'
    icon = 'exchange-alt'
    area = 'Gestão de Pessoas'
