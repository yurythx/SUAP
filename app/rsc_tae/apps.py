from djtools.apps import SuapAppConfig as AppConfig


class RscTaeConfig(AppConfig):
    default = True
    name = 'rsc_tae'
    verbose_name = 'RSC-TAE'
    description = 'Gerencia os dados e fluxos ao processo de concessão de Reconhecimento de Saberes e Competências aos técnicos-administrativos.'
    area = 'Gestão de Pessoas'
