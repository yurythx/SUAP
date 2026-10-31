from djtools.apps import SuapAppConfig as AppConfig


class DocumentoEletronicoConfig(AppConfig):
    default = True
    name = 'documento_eletronico'
    verbose_name = 'Documentos Eletrônicos'
    area = 'Documentos e Processos Eletrônicos'

    def ready(self):
        import documento_eletronico.signals  # register the signals

        assert documento_eletronico.signals
