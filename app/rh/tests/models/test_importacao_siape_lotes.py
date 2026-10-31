"""Divisão de um layout em lotes por chave de partição."""

from rh.importacao_siape.layouts import por_campo, por_cpf_da_matricula
from rh.importacao_siape.lotes import chave_de_particao, dividir_em_lotes


def test_pequeno_ou_sem_chave_fica_num_unico_lote():
    itens = [{'x': str(i)} for i in range(10)]

    sem_chave = dividir_em_lotes(itens, None)
    assert len(sem_chave) == 1
    assert sem_chave[0].numero == 1
    assert sem_chave[0].indices == tuple(range(10))

    chave = chave_de_particao(por_campo('x'))
    pequeno = dividir_em_lotes(itens, chave, tamanho=100)
    assert len(pequeno) == 1
    assert pequeno[0].indices == tuple(range(10))

    vazio = dividir_em_lotes([], chave)
    assert len(vazio) == 1
    assert vazio[0].numero == 1
    assert vazio[0].indices == ()


def test_grande_nenhuma_chave_fica_partida_entre_lotes():
    chaves = ['a', 'b', 'a', 'c', 'c', 'c', 'd', 'b']
    itens = [{'chave': c} for c in chaves]
    chave = chave_de_particao(por_campo('chave'))

    lotes = dividir_em_lotes(itens, chave, tamanho=3)

    chaves_por_lote = [{chaves[i] for i in lote.indices} for lote in lotes]
    todas_as_chaves_vistas: set[str] = set()
    for chaves_do_lote in chaves_por_lote:
        assert not (chaves_do_lote & todas_as_chaves_vistas), 'uma chave apareceu em mais de um lote'
        todas_as_chaves_vistas |= chaves_do_lote

    todos_os_indices = [indice for lote in lotes for indice in lote.indices]
    assert sorted(todos_os_indices) == list(range(len(itens)))
    for lote in lotes:
        assert list(lote.indices) == sorted(lote.indices)
    for lote in lotes[:-1]:
        assert len(lote.indices) >= 3
    assert [lote.numero for lote in lotes] == list(range(1, len(lotes) + 1))


def test_chave_de_particao_por_cpf_da_matricula():
    # '262180111111' e '362180222222' extraem matrículas DIFERENTES ('111111' e '222222': os
    # 7 últimos dos 12 primeiros dígitos) — o mesmo servidor pode ter mais de uma matrícula.
    cpf_por_matricula = {'111111': '111.111.111-11', '222222': '111.111.111-11'}
    chave = chave_de_particao(por_cpf_da_matricula('GR-MATRICULA'), cpf_por_matricula=cpf_por_matricula)

    mesma_pessoa_1 = chave({'GR-MATRICULA': '262180111111'})
    mesma_pessoa_2 = chave({'GR-MATRICULA': '362180222222'})
    sem_servidor = chave({'GR-MATRICULA': '262180999999'})

    assert mesma_pessoa_1 == mesma_pessoa_2 == '111.111.111-11'
    assert sem_servidor == 'matricula:999999'


def test_layout_dividido_tem_ao_menos_um_lote_por_worker_sem_lote_menor_que_o_piso():
    itens = [{'chave': str(i)} for i in range(9031)]
    chave = chave_de_particao(por_campo('chave'))

    # como o servidor1 real: 9.031 linhas, lote de 5.000 e 4 workers
    lotes = dividir_em_lotes(itens, chave, tamanho=5000, minimo_de_lotes=4)
    assert len(lotes) == 4
    assert sorted(i for lote in lotes for i in lote.indices) == list(range(9031))

    # o piso impede lotes pequenos demais: com piso de 3.000, 9.031 linhas dão 3 lotes, não 4
    assert len(dividir_em_lotes(itens, chave, tamanho=5000, minimo_de_lotes=4, tamanho_minimo=3000)) == 3

    # layout grande não ganha lotes a mais: o tamanho configurado continua valendo
    grandes = [{'chave': str(i)} for i in range(50000)]
    assert len(dividir_em_lotes(grandes, chave, tamanho=5000, minimo_de_lotes=4)) == 10
