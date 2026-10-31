from djtools.apps import SuapAppConfig as AppConfig


class AvaliacaoCursosConfig(AppConfig):
    default = True
    name = 'avaliacao_cursos'
    verbose_name = 'Avaliação de Cursos'
    description = 'Avalia o desempenho de cursos pelos alunos, docentes e técnicos administrativos.'
    icon = 'percent'
    area = 'Desenvolvimento Institucional'
