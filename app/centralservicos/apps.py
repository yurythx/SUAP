from djtools.apps import SuapAppConfig as AppConfig
from centralservicos.signals import signals_estatisticas


class CentralServicosConfig(AppConfig):
    default = True
    name = 'centralservicos'
    verbose_name = 'Central de Serviços'
    description = 'Gerencia a Central de Serviços para abertura de chamados para as diferentes áreas de atuação da instituição.'
    icon = 'concierge-bell'
    area = 'Comum'

    def ready(self):
        signals_estatisticas()
