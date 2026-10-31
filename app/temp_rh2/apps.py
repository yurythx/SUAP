from djtools.apps import SuapAppConfig as AppConfig


class CompeticoesDesportivasConfig(AppConfig):
    default = True
    name = 'temp_rh2'
    verbose_name = 'Competições Desportivas'
    description = 'Gerencia os dados e fluxos específicos das competições esportivas entre os servidores.'
    icon = 'futbol'
    area = 'Gestão de Pessoas'
