from rh.deduplicacao.aplicacao import PlanoDesatualizado, _motivo


def test_erro_de_programacao_nao_se_passa_por_plano_desatualizado() -> None:
    assert 'rode planejar' not in _motivo(KeyError('nome_mae'))


def test_plano_desatualizado_manda_replanejar_com_os_ids() -> None:
    assert _motivo(PlanoDesatualizado('PF do plano não existe mais: 7, 9')) == 'PF do plano não existe mais: 7, 9; rode planejar de novo'
