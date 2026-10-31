from djtools.apps import SuapAppConfig as AppConfig


class FeriasConfig(AppConfig):
    default = True
    name = 'ferias'
    verbose_name = 'Férias'
    description = 'Permite a visualização dados das férias dos servidores conforme os dados importados do SIAPE.'
    icon = 'umbrella-beach'
    area = 'Gestão de Pessoas'
