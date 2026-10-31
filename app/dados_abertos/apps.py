from djtools.apps import SuapAppConfig as AppConfig


class DadosAbertosConfig(AppConfig):
    default = True
    name = 'dados_abertos'
    verbose_name = 'Dados Abertos'
    description = 'Gerencia os cadastros e principais funcionalidades relacionadas a Dados Abertos.'
    icon = 'database'
    area = 'Tecnologia da Informação'
