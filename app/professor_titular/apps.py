from djtools.apps import SuapAppConfig as AppConfig


class ProfessorTitularConfig(AppConfig):
    default = True
    name = 'professor_titular'
    verbose_name = 'Professor Titular'
    description = 'Gerencia os dados e fluxos do processo de promoção do docente a classe de Professor Titular.'
    icon = 'chalkboard-teacher'
    area = 'Gestão de Pessoas'
