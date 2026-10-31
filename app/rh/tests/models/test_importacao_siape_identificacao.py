"""Identificação do layout de um arquivo .REF do extrator."""

from rh.importacao_siape.identificacao import carregar_refs, identificar


def test_reconhece_ref_mesmo_com_espacos_diferentes():
    refs = carregar_refs()
    conteudo = refs['estado_civil'].replace('   ', '\t')

    assert identificar(conteudo, refs).layout == 'estado_civil'


def test_ref_alterado_aponta_o_layout_mais_proximo_e_os_campos_divergentes():
    refs = carregar_refs()
    alterado = refs['estado_civil'].replace('IT-NO-ESTADO-CIVIL', 'IT-DS-ESTADO-CIVIL')

    identificacao = identificar(alterado, refs)

    assert identificacao.layout is None
    assert 'estado_civil' in identificacao.diagnostico
    assert 'IT-DS-ESTADO-CIVIL' in identificacao.diagnostico
    assert 'IT-NO-ESTADO-CIVIL' in identificacao.diagnostico
