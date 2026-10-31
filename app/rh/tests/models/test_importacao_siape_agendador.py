"""Agendador que executa um grafo de dependências em paralelo."""

import threading
import time
from functools import partial

import pytest

from rh.importacao_siape.agendador import executar_etapas, executar_grafo

GRAFO = {'a': set(), 'b': set(), 'c': {'a'}, 'd': {'c'}, 'e': {'b'}}


@pytest.mark.parametrize('workers', [1, 3])
def test_respeita_precedencias_e_pula_dependentes_de_falha(workers):
    inicio, fim = {}, {}

    def executar(nome):
        inicio[nome] = time.monotonic()
        time.sleep(0.01)
        fim[nome] = time.monotonic()
        if nome == 'c':
            raise RuntimeError('quebrou')

    pulados = []
    resultado = executar_grafo(GRAFO, executar, workers, ao_pular=lambda nome, motivo: pulados.append(nome))

    assert set(resultado.concluidos) == {'a', 'b', 'e'}
    assert set(resultado.falhos) == {'c'}
    assert resultado.pulados == {'d': 'Dependência c não foi concluída.'}
    assert pulados == ['d']
    assert inicio['c'] >= fim['a']
    assert inicio['e'] >= fim['b']


def test_independentes_rodam_ao_mesmo_tempo():
    barreira = threading.Barrier(2, timeout=2)

    resultado = executar_grafo({'a': set(), 'b': set()}, lambda nome: barreira.wait(), workers=2)

    assert set(resultado.concluidos) == {'a', 'b'}


def test_unidades_de_nos_diferentes_intercalam():
    barreira = threading.Barrier(4, timeout=2)

    def unidade():
        barreira.wait()

    def expandir(nome):
        return [[unidade, unidade]]

    resultado = executar_etapas({'a': set(), 'b': set()}, expandir, workers=4)

    assert set(resultado.concluidos) == {'a', 'b'}


@pytest.mark.parametrize('workers', [1, 3])
def test_etapa_com_falha_completa_as_demais_unidades_e_para_o_no(workers):
    executadas = []
    finalizados = []

    def u1():
        executadas.append('u1')

    def u2_falha():
        executadas.append('u2')
        raise RuntimeError('quebrou')

    def u3():
        executadas.append('u3')

    def u4():
        executadas.append('u4')

    def expandir(nome):
        if nome == 'a':
            return [[u1, u2_falha, u3], [u4]]
        return [[lambda: None]]

    resultado = executar_etapas(
        {'a': set(), 'b': {'a'}},
        expandir,
        workers,
        ao_finalizar=lambda nome, erro: finalizados.append((nome, erro)),
    )

    assert set(executadas) == {'u1', 'u2', 'u3'}
    assert 'a' in resultado.falhos
    assert resultado.pulados == {'b': 'Dependência a não foi concluída.'}
    assert len(finalizados) == 1
    nome_finalizado, erro_finalizado = finalizados[0]
    assert nome_finalizado == 'a'
    assert isinstance(erro_finalizado, RuntimeError)


@pytest.mark.parametrize('workers', [1, 3])
def test_dependente_so_comeca_apos_todas_as_etapas_do_no_anterior(workers):
    inicio, fim = {}, {}

    def unidade(rotulo):
        inicio[rotulo] = time.monotonic()
        time.sleep(0.01)
        fim[rotulo] = time.monotonic()

    def expandir(nome):
        if nome == 'a':
            return [[partial(unidade, 'a-e1-1'), partial(unidade, 'a-e1-2')], [partial(unidade, 'a-e2')]]
        return [[partial(unidade, 'b')]]

    executar_etapas({'a': set(), 'b': {'a'}}, expandir, workers)

    assert inicio['a-e2'] >= fim['a-e1-1']
    assert inicio['a-e2'] >= fim['a-e1-2']
    assert inicio['b'] >= fim['a-e1-1']
    assert inicio['b'] >= fim['a-e1-2']
    assert inicio['b'] >= fim['a-e2']


def test_callback_que_falha_na_thread_principal_cancela_unidades_ainda_na_fila():
    """`ao_pular` estourando não pode deixar as unidades já submetidas ao pool rodarem até o fim.

    `a` falha quase instantaneamente e arrasta `b` (que depende dela) para `_pular_dependentes`,
    de onde `ao_pular` estoura na thread principal. Nesse momento `d` (independente) já submeteu
    suas unidades ao pool de 2 workers: só 2 delas alcançam a rodar antes da falha; as demais
    devem ser canceladas em vez de completadas pelo `shutdown` do pool.
    """
    executadas_d = []
    trava = threading.Lock()

    def unidade_d():
        time.sleep(0.05)
        with trava:
            executadas_d.append(1)

    def unidade_a():
        raise RuntimeError('a quebrou')

    def expandir(nome):
        if nome == 'a':
            return [[unidade_a]]
        return [[unidade_d] * 6]

    def ao_pular_que_falha(nome, motivo):
        raise RuntimeError('ao_pular quebrou')

    with pytest.raises(RuntimeError, match='ao_pular quebrou'):
        executar_etapas({'a': set(), 'b': {'a'}, 'd': set()}, expandir, workers=2, ao_pular=ao_pular_que_falha)

    assert len(executadas_d) < 6


@pytest.mark.parametrize('etapas_do_no_a', [[], [[]]])
@pytest.mark.parametrize('workers', [1, 3])
def test_no_sem_etapas_libera_dependentes_sem_travar_nem_dar_falso_ciclo(workers, etapas_do_no_a):
    def expandir(nome):
        return etapas_do_no_a if nome == 'a' else [[lambda: None]]

    resultado = executar_etapas({'a': set(), 'b': {'a'}}, expandir, workers)

    assert set(resultado.concluidos) == {'a', 'b'}
    assert not resultado.falhos
    assert not resultado.pulados
