"""Stub do ``manage.py gerar_banco_mock``: materializa os seeds e2e de sessão do edu.

Só é coletado com ``-m mock`` (ver ``_deselecionar_mock`` no ``conftest.py`` raiz).
"""

import pytest


@pytest.mark.mock
@pytest.mark.django_db(databases='__all__')
def test_mock(edu_seed, seed_periodo_executado, seed_periodo_fechado, seed_matricula_renovada, seed_conceito, seed_de_rotas) -> None:
    """Pede as fixtures de seed; o corpo é vazio de propósito."""
