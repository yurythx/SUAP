"""Fixtures dos e2e de fluxo transversal (login, permissão, autocomplete...).

O conteúdo mora em ``djtools/e2e_fixtures.py`` para que qualquer módulo possa reusar via
o mesmo star-import. Ver a docstring de lá para o porquê de não ser plugin global.
"""

import pytest

from djtools.e2e_fixtures import *  # noqa: F403
from djtools.e2e_fixtures import semear_base, servidor_com_login

# Matrículas próprias, fora das do seed do behave: num banco com os dois seeds (``pytest -m
# e2e`` inteiro), o `get_or_create` da factory reencontraria o servidor de lá, com outro setor.
SERVIDOR_SEM_GRUPO = '7000001'
SERVIDOR_CHEFE = '7000002'


@pytest.fixture(scope='session')
def e2e_seed(e2e_banco):
    """Seed por factories (#17486): a base, dois servidores sem grupo, lotados na raiz, e uma pessoa jurídica."""
    from rh.tests.factories import PessoaJuridicaFactory

    raiz = semear_base()
    servidor_com_login(SERVIDOR_SEM_GRUPO, raiz)
    servidor_com_login(SERVIDOR_CHEFE, raiz)
    # O gate de acessibilidade audita a listagem de PJ com linhas, sem depender da ordem de ``test_cadastro``.
    PessoaJuridicaFactory()
