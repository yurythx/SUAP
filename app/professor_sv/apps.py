from djtools.apps import SuapAppConfig as AppConfig


class ProgramaGestaoConfig(AppConfig):
    default = True
    name = 'professor_sv'
    verbose_name = 'Professor Substituto/Visitante'
    area = 'Gestão de Pessoas'
    description = 'Módulo de Gestão de Vagas, Seleção e Alocação de vagas Professor Substituto/Visitante.'
