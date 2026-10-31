from djtools.apps import SuapAppConfig as AppConfig


class AuditoriaConfig(AppConfig):
    default = True
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'auditoria'
    verbose_name = 'Auditoria'
    area = 'Auditoria'
    description = 'É responsável pelo planejamento e monitoramento das ações de Auditoria'
    icon = 'search-plus'

    def ready(self):
        import auditoria.signals

        assert auditoria.signals
