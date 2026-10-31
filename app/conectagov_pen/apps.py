from djtools.apps import SuapAppConfig as AppConfig


class ConectagovPenConfig(AppConfig):
    default = True
    name = 'conectagov_pen'
    verbose_name = 'Integração API ConectaGov - Barramento PEN'
    area = 'Documentos e Processos Eletrônicos'
