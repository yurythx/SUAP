from djtools.apps import SuapAppConfig as AppConfig


class RscConfig(AppConfig):
    default = True
    name = 'rsc'
    verbose_name = 'RSC'
    description = 'Gerencia os dados e fluxos ao processo de concessão de Reconhecimento de Saberes e Competências aos docentes.'
    area = 'Gestão de Pessoas'
