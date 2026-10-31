"""Testes das funções de agregação do process mining.

São funções puras (sem banco) que transformam pares setor/tempo no formato
consumido pelos gráficos e pela tabela do relatório. Antes estas funções eram
copiadas para o teste e o resultado não era verificado; aqui importamos a
implementação real de `processmining.views` e checamos a agregação.
"""

from processmining.views import gerar_tabela, get_tempo_em_cada_setor

SETORES = ['A', 'B', 'A']
TEMPOS_EFETIVOS = [1.0, 2.0, 3.0]
TEMPOS_HANDOFF = [0.5, 1.5, 0.5]


def test_get_tempo_em_cada_setor_soma_repeticoes():
    """Cada setor aparece uma vez, com a soma dos tempos das suas ocorrências."""
    resultado = get_tempo_em_cada_setor(SETORES, TEMPOS_EFETIVOS)

    assert resultado == [{'name': 'A', 'y': 4.0}, {'name': 'B', 'y': 2.0}]


def test_gerar_tabela_agrega_tempos_e_percentuais_por_setor():
    tabela = {linha['setor']: linha for linha in gerar_tabela(SETORES, TEMPOS_EFETIVOS, TEMPOS_HANDOFF)}

    setor_a = tabela['A']
    assert setor_a['repeticao'] == 2
    assert setor_a['tempo_efetivo'] == 4.0
    assert setor_a['tempo_handoff'] == 1.0
    assert setor_a['tempo_total'] == 5.0
    # Percentual relativo ao total de todos os setores (efetivo total = 6, handoff total = 2.5).
    assert round(setor_a['percent_efetivo'], 2) == 66.67
    assert setor_a['percent_handoff'] == 40.0
