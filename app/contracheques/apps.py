from djtools.apps import SuapAppConfig as AppConfig


class ContrachequesConfig(AppConfig):
    default = True
    name = 'contracheques'
    verbose_name = 'Contracheques'
    description = 'Permite a visualização dos contracheques dos servidores conforme os dados importados do SIAPE.'
    icon = 'coins'
    area = 'Gestão de Pessoas'
