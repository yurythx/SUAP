from djtools.apps import SuapAppConfig as AppConfig


class CnpqConfig(AppConfig):
    default = True
    name = 'cnpq'
    verbose_name = 'CNPQ'
    description = 'Faz a integração do SUAP com o CNPQ para importação de currículos Lattes e indicadores.'
    icon = 'globe'
    area = 'Pesquisa e Inovação'
