from djtools.apps import SuapAppConfig as AppConfig


class FinanceiroConfig(AppConfig):
    default = True
    name = 'financeiro'
    verbose_name = 'Financeiro'
    description = 'Gerencia o financeiro da instituição.'
    icon = 'dollar-sign'
    area = 'Administração'
