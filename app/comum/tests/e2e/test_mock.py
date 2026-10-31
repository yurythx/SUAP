"""Stub do ``manage.py gerar_banco_mock``: materializa os seeds e2e de sessão do comum.

Só é coletado com ``-m mock`` (ver ``_deselecionar_mock`` no ``conftest.py`` raiz).

As três fixtures de sessão do módulo são encadeadas (`predio_e2e` pede `campus_e2e`), mas
todas são pedidas explicitamente: é a lista que documenta o que o dump leva do comum, e
pedir só a folha esconderia a remoção de um elo.
"""

import pytest


@pytest.mark.mock
@pytest.mark.django_db(databases='__all__')
def test_mock(servidores_comum, campus_e2e, predio_e2e) -> None:
    """Pede as fixtures de seed; o corpo é vazio de propósito."""
