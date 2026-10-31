"""Substrato dos testes do CNPq.

O módulo usava o `suap_data` por um servidor autenticado e pelas tabelas-tipo que o
`_criar_servidor_cnpq` consulta por código (`Setor` A1 nas duas árvores, `Situacao`,
`JornadaTrabalho` e `CargoEmprego`). As factories do `rh` criam exatamente essas linhas,
com os mesmos códigos, então as consultas do teste continuam valendo.
"""

import pytest

from rh.tests.factories import (
    CargoEmpregoFactory,
    JornadaTrabalhoFactory,
    ServidorFactory,
    SetorFactory,
    SetorSiapeFactory,
    SituacaoFactory,
)

SENHA = '123'


@pytest.fixture
def substrato_cnpq(db, sync_permissions):
    """Servidor autenticável e as linhas-tipo que o teste busca por código."""
    setor_suap = SetorFactory(sigla='A1', nome='A1')
    SetorSiapeFactory(sigla='A1', nome='A1', codigo='A1')
    SituacaoFactory()
    JornadaTrabalhoFactory()
    CargoEmpregoFactory()

    servidor = ServidorFactory(setor=setor_suap)
    user = servidor.get_user()
    user.set_password(SENHA)
    user.save()
    return servidor
