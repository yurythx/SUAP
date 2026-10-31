from djtools.apps import SuapAppConfig as AppConfig


class AcervoAcademicoConfig(AppConfig):
    default = True
    name = 'acervo_academico'
    verbose_name = 'Acervo Acadêmico'
    description = 'Gerencia as rotinas de importação de dossiês digitalizados de alunos.'
    area = 'Ensino'
    icon = 'folder-open'

    def ready(self):
        import acervo_academico.signals  # register the signals

        assert acervo_academico.signals
