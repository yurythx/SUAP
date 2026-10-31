from djtools.apps import SuapAppConfig as AppConfig


class PafcConfig(AppConfig):
    default = True
    name = 'pafc'
    verbose_name = 'Projeto de Autorização de Funcionamento de Curso'
    area = 'Ensino'
    description = 'Gerencia a elaboração de projeto de autorização de funcionamento de curso'
    icon = 'chalkboard-teacher'

    def ready(self):
        import pafc.signals  # registra os sinais

        assert pafc.signals
