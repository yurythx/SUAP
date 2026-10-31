from djtools.apps import SuapAppConfig as AppConfig


class PdiConfig(AppConfig):
    default = True
    name = 'pdi'
    verbose_name = 'PDI'
    description = 'Gerencia o Plano de Desenvolvimento Institucional.'
    icon = 'percentage'
    area = 'Desenvolvimento Institucional'
