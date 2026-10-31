from djtools.apps import SuapAppConfig as AppConfig


class OrcamentoConfig(AppConfig):
    default = True
    name = 'orcamento'
    verbose_name = 'Orçamento'
    description = 'Controla o orçamento da instituição.'
    icon = 'dollar-sign'
    area = 'Desenvolvimento Institucional'
