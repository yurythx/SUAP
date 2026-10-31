from djtools.apps import SuapAppConfig as AppConfig


class GestaoConfig(AppConfig):
    default = True
    name = 'gestao'
    verbose_name = 'Gestão'
    description = 'Controla variáveis e indicadores de Gestão.'
    icon = 'percentage'
    area = 'Desenvolvimento Institucional'
