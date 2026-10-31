from django.dispatch import Signal

signal = Signal()  # providing_args=['request', 'data']


def emissao_documentos():
    def receive_function(func):
        def emissao_documentos_wrapper(sender, request, data, **kwargs):
            return func(request, data)

        signal.connect(emissao_documentos_wrapper)
        return emissao_documentos_wrapper

    return receive_function
