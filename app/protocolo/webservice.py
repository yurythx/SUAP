from protocolo.views import processo_consulta_publica


def get_processo(numero_processo, documento):
    return processo_consulta_publica(numero_processo, documento)


exposed = [[get_processo, 'get_processo']]
