"""Substrato dos testes do Processo Eletrônico.

O módulo usava o `suap_data` por três peças apenas: um setor SUAP, dois servidores (para
ter dois vínculos distintos) e um superusuário. Aqui elas vêm das factories do `rh`.
"""

from types import SimpleNamespace

import pytest

from processo_eletronico.models import Processo
from rh.tests.factories import ServidorFactory, SetorFactory


@pytest.fixture
def setor_com_siorg(db):
    """Setor de criação de processo.

    O NUP é gerado no `save` a partir do código SIORG do setor (herdado do superior quando
    ausente), então o setor precisa tê-lo — era o que o teste setava à mão no `suap_data`.
    """
    return SetorFactory(codigo_siorg=str(Processo.CODIGO_SIORG))


@pytest.fixture
def dois_servidores(db, sync_permissions, setor_com_siorg):
    """Dois servidores no mesmo setor: o que interessa é haver dois vínculos distintos."""
    return SimpleNamespace(
        a=ServidorFactory(setor=setor_com_siorg),
        b=ServidorFactory(setor=setor_com_siorg),
    )
