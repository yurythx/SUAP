"""Contagem de progresso e captura de ocorrências de um layout em execução."""

import logging
import threading

from rh.importacao_siape.progresso import ItensComProgresso, capturando_ocorrencias

log = logging.getLogger('rh.importador')


def test_progresso_nao_regride_quando_o_layout_percorre_os_itens_duas_vezes():
    reportados = []
    itens = ItensComProgresso([{'n': i} for i in range(10)], reportados.append, passo=3)

    for _ in itens:
        pass
    list(itens)  # segunda passada, como em importar_cargo_emprego

    assert reportados == [3, 6, 9, 10]


def test_captura_so_as_ocorrencias_da_propria_thread_com_a_linha(logging_habilitado):
    registradas = []
    itens = ItensComProgresso([{}, {}, {}], lambda n: None)

    with capturando_ocorrencias(lambda *args: registradas.append(args), itens):
        for indice, _ in enumerate(itens, start=1):
            if indice == 2:
                log.warning('matrícula %s sem setor', '123')
        outra = threading.Thread(target=lambda: log.error('de outro layout'))
        outra.start()
        outra.join()
        log.info('informativo não entra')

    assert registradas == [('warning', 2, 'matrícula 123 sem setor')]
