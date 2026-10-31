from django.dispatch import Signal

signal = Signal()


def registrar_acao():
    def receive_function(func):
        def registrar_acao_wrapper(sender, request, data, datahora_inicio, datahora_fim, **kwargs):
            return func(request, data, datahora_inicio, datahora_fim)

        signal.connect(registrar_acao_wrapper)
        return registrar_acao_wrapper

    return receive_function
