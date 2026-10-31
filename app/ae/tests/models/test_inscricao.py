"""Testes DB-free de ``Inscricao.possui_parecer`` (usada pela ficha e pela listagem admin)."""

import pytest

from ae.models import Inscricao


def test_inscricao_nova_nao_possui_parecer():
    # o default do campo é SEM_PARECER — string não vazia, por isso o template não pode testar só a truthiness
    assert Inscricao().situacao_parecer == Inscricao.SEM_PARECER
    assert Inscricao().possui_parecer is False


@pytest.mark.parametrize('situacao', [Inscricao.DEFERIDO, Inscricao.PENDENTE_DOCUMENTACAO])
def test_inscricao_com_situacao_registrada_possui_parecer(situacao):
    assert Inscricao(situacao_parecer=situacao).possui_parecer is True
