from rh.deduplicacao.campos import campos_mesclaveis, resolver_campos


def test_preenche_vazio_do_vencedor_com_a_perdedora_mais_recente() -> None:
    preenchimentos, descartes = resolver_campos({'pk': 1, 'rg': None}, [{'pk': 2, 'rg': '111'}, {'pk': 3, 'rg': '222'}])

    assert preenchimentos == {'rg': '222'}
    assert descartes == [(2, 'rg', '111')]


def test_valor_do_vencedor_prevalece_e_o_diferente_vai_para_auditoria() -> None:
    preenchimentos, descartes = resolver_campos({'pk': 1, 'nome_mae': 'Maria'}, [{'pk': 2, 'nome_mae': 'Joana'}, {'pk': 3, 'nome_mae': 'Maria'}])

    assert preenchimentos == {}
    assert descartes == [(2, 'nome_mae', 'Joana')]


def test_passaporte_so_e_auditado() -> None:
    preenchimentos, descartes = resolver_campos({'pk': 1, 'passaporte': None}, [{'pk': 2, 'passaporte': 'AB123456'}])

    assert preenchimentos == {}
    assert descartes == [(2, 'passaporte', 'AB123456')]


def test_biometria_vazia_e_preenchida_pela_perdedora() -> None:
    preenchimentos, descartes = resolver_campos({'pk': 1, 'template': b''}, [{'pk': 2, 'template': memoryview(b'\x01')}])

    assert preenchimentos == {'template': b'\x01'}
    assert descartes == []


def test_biometria_e_senha_divergentes_vao_para_auditoria_sem_o_valor() -> None:
    vencedor = {'pk': 1, 'template': b'\x01', 'senha_ponto': 'abc'}
    perdedora = {'pk': 2, 'template': memoryview(b'\x02'), 'senha_ponto': 'xyz'}

    preenchimentos, descartes = resolver_campos(vencedor, [perdedora])

    assert preenchimentos == {}
    assert descartes == [(2, 'senha_ponto', None), (2, 'template', None)]


def test_biometria_igual_compara_pelo_conteudo() -> None:
    assert resolver_campos({'pk': 1, 'template': b'\x01'}, [{'pk': 2, 'template': memoryview(b'\x01')}]) == ({}, [])


def test_campos_de_identidade_e_derivados_nao_se_mesclam() -> None:
    campos = set(campos_mesclaveis())

    assert not campos & {'cpf', 'documento_identificador', 'nome', 'uuid', 'eh_servidor', 'eh_aluno', 'eh_prestador', 'eh_usuarioexterno'}
    assert {'nascimento_data', 'nome_mae', 'template', 'senha_ponto'} <= campos


def test_marca_de_origem_da_digital_acompanha_a_digital() -> None:
    """A digital vem da perdedora: a marca 'importada do terminal' vem com ela, em vez de ficar o False da sobrevivente sem digital."""
    vencedor = {'pk': 1, 'template': None, 'template_importado_terminal': False}
    perdedora = {'pk': 2, 'template': b'digital', 'template_importado_terminal': True}

    preenchimentos, descartes = resolver_campos(vencedor, [perdedora])

    assert preenchimentos == {'template': b'digital', 'template_importado_terminal': True}
    assert descartes == []


def test_marca_de_origem_fica_com_a_digital_da_sobrevivente() -> None:
    vencedor = {'pk': 1, 'template': b'minha', 'template_importado_terminal': False}
    perdedora = {'pk': 2, 'template': b'outra', 'template_importado_terminal': True}

    preenchimentos, descartes = resolver_campos(vencedor, [perdedora])

    assert preenchimentos == {}
    assert descartes == [(2, 'template', None), (2, 'template_importado_terminal', True)]
