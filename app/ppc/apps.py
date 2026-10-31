from djtools.apps import SuapAppConfig as AppConfig


class PpcConfig(AppConfig):
    default = True
    name = 'ppc'
    verbose_name = 'Projeto Pedagógico de Curso'
    area = 'Ensino'
    description = 'Gerencia a elaboaração de projetos pedagógico de curso.'
    icon = 'chalkboard-teacher'
