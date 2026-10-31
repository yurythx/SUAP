from djtools.apps import SuapAppConfig as AppConfig


class CpaConfig(AppConfig):
    default = True
    name = 'cpa'
    verbose_name = 'CPA'
    description = 'Gerencia a CPA.'
    icon = 'percentage'
    area = 'Desenvolvimento Institucional'
