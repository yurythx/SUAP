from djtools.apps import SuapAppConfig as AppConfig


class ProgressaoDocenteConfig(AppConfig):
    default = True
    name = 'progressao_docente'
    verbose_name = 'Progressão Docente'
    description = 'Gerencia os dados e fluxos do processo de promoção e progressão do docente.'
    icon = 'chalkboard-teacher'
    area = 'Gestão de Pessoas'

    def ready(self):
        import progressao_docente.signals

        assert progressao_docente.signals
