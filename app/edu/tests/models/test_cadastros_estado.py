"""Teste unitário (sem DB) de ``Estado.get_sigla`` (lookup no dict literal ``ESTADOS``)."""

from edu.models.cadastros_gerais import Estado


def test_get_sigla_encontra_pela_chave_id():
    estado = Estado(id=24)  # Rio Grande do Norte em Estado.ESTADOS
    assert estado.get_sigla() == 'RN'


def test_get_sigla_none_para_id_inexistente():
    estado = Estado(id=99999)
    assert estado.get_sigla() is None
