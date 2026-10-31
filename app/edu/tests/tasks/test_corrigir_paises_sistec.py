import importlib

import pytest
from django.apps import apps

from edu.models import Pais
from edu.tests.factories import CidadeFactory, PaisFactory

migracao = importlib.import_module('edu.migrations.0332_corrigir_paises_sistec')


def _paises() -> set[tuple[str, str]]:
    return set(Pais.objects.values_list('sigla', 'nome'))


@pytest.mark.django_db
def test_irlanda_e_nomes_corrigidos_e_antilhas_sem_uso_removidas():
    PaisFactory(sigla='IRL', nome='Irlanda Do Norte')
    PaisFactory(sigla='VNM', nome='Vietnã Do Sul')
    PaisFactory(sigla='ANT', nome='Antilhas Holandesas')
    PaisFactory(sigla='ANT', nome='Estados Assoc. Das Antilhas')

    migracao.corrigir(apps, None)

    assert _paises() == {('IRL', 'Irlanda'), ('GBR', 'Irlanda Do Norte'), ('VNM', 'Vietnã'), ('ANT', 'Antilhas Holandesas')}


@pytest.mark.django_db
def test_antilhas_referenciadas_ficam_e_base_vazia_nao_ganha_linhas():
    CidadeFactory(pais=PaisFactory(sigla='ANT', nome='Estados Assoc. Das Antilhas'))

    migracao.corrigir(apps, None)

    assert _paises() == {('ANT', 'Estados Assoc. Das Antilhas')}
