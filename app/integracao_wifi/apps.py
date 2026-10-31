from djtools.apps import SuapAppConfig as AppConfig


class DispositivosIotConfig(AppConfig):
    default = True
    name = 'integracao_wifi'
    verbose_name = 'Integração com Serviço WiFi'
    description = 'Gera tokens para acesso à rede wi-fi "dispositivos-iot" e chaves de wi-fi para os módulos de visitantes e de eventos.'
    icon = 'wifi'
    area = 'Tecnologia da Informação'
