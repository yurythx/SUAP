from djtools.apps import SuapAppConfig as AppConfig


class ProgramaGestaoConfig(AppConfig):
    default = True
    name = 'sigepe_ocorrencias'
    verbose_name = 'Sigepe Ocorrências'
    area = 'Gestão de Pessoas'
    icon = 'hourglass-start'
    description = 'Gera arquivos de importação para o Sigepe Ocorrências'
