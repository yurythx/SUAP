"""Grafo de precedência dos layouts do extrator SIAPE."""

from rh.importacao_siape.layouts import LAYOUTS, dependencias_efetivas, ordem_topologica


def test_ordem_topologica_respeita_as_dependencias_e_omite_inativos():
    ordem = ordem_topologica()

    for nome in ordem:
        for dependencia in LAYOUTS[nome].dependencias:
            if LAYOUTS[dependencia].ativo:
                assert ordem.index(dependencia) < ordem.index(nome), f'{dependencia} deveria vir antes de {nome}'
    assert 'historico_afastamento' not in ordem
    assert set(ordem) == {nome for nome, layout in LAYOUTS.items() if layout.ativo}


def test_dependencia_efetiva_atravessa_layout_nao_selecionado():
    # servidorafastamentos -> ... -> servidor1 -> afastamentos: sem o núcleo selecionado,
    # a tabela ainda precisa terminar antes.
    assert dependencias_efetivas('servidorafastamentos', {'afastamentos', 'servidorafastamentos'}) == {'afastamentos'}
    assert dependencias_efetivas('servidorafastamentos', {'servidorafastamentos'}) == set()
    assert dependencias_efetivas('servidor3', {'servidor1', 'servidor2', 'servidor3'}) == {'servidor2'}


def test_servidor2_e_historico_funcao_nao_tem_particao():
    # os dois gravam ServidorFuncaoHistorico (update_or_create): o post_save de
    # processo_eletronico mexe em todo o setor da função, não só na linha — a partição por
    # CPF/matrícula não protege esse efeito colateral (ver rh.importacao_siape.layouts._PARTICOES
    # e o deadlock que isso causava entre lotes de setores diferentes).
    assert LAYOUTS['servidor2'].particao is None
    assert LAYOUTS['historico_funcao'].particao is None
    # servidor3 não grava ServidorFuncaoHistorico: continua dividido
    assert LAYOUTS['servidor3'].particao is not None
