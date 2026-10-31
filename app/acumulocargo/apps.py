from djtools.apps import SuapAppConfig as AppConfig


class AcumuloCargoConfig(AppConfig):
    default = True
    name = 'acumulocargo'
    verbose_name = 'Acúmulo de Cargos'
    description = 'É responsável pela aplicação do questionário de acúmulo de cargos.'
    icon = 'user-tie'
    area = 'Gestão de Pessoas'
