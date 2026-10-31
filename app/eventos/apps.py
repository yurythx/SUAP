from djtools.apps import SuapAppConfig as AppConfig


class EventosConfig(AppConfig):
    default = True
    name = 'eventos'
    verbose_name = 'Eventos'
    description = 'Gerencia o cadastro eventos, permitindo controlar participantes e gerar certificados.'
    icon = 'calendar-week'
    area = 'Comunicação Social'

    def ready(self):
        import eventos.signals

        assert eventos.signals
