from djtools.apps import SuapAppConfig as AppConfig


class CursosConfig(AppConfig):
    default = True
    name = 'cursos'
    verbose_name = 'Cursos e Concursos'
    description = 'Gerencia os dados e fluxos referentes aos cursos e concursos realizados. Os principais fluxos e dados gerenciados são referentes ao cadastro dos parcipantes, horas trabalhadas e pagamento.'
    icon = 'user-check'
    area = 'Gestão de Pessoas'
