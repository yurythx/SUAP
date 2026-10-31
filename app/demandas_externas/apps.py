from djtools.apps import SuapAppConfig as AppConfig


class DemandasExternasConfig(AppConfig):
    default = True
    name = 'demandas_externas'
    verbose_name = 'Demandas Externas'
    description = 'Gerencia as demandas externas de extensão.'
    icon = 'external-link-square-alt'
    area = 'Extensão'
