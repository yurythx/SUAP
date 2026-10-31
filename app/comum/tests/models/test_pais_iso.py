import re

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command

from comum.models import Pais
from comum.management.commands.preencher_iso_paises import ISO_ALFA3_POR_CODIGO_SIAPE

USADOS_POR_ESTRANGEIROS = {
    '011': 'ARG',
    '024': 'BRA',
    '036': 'CHL',
    '040': 'COL',
    '053': 'ECU',
    '054': 'ESP',
    '129': 'PRT',
    '163': 'URY',
    '271': 'GBR',
}


def test_tabela_so_tem_alfa3_valido() -> None:
    assert all(re.fullmatch(r'[A-Z]{3}', iso) for iso in ISO_ALFA3_POR_CODIGO_SIAPE.values())


def test_paises_dos_estrangeiros_estao_na_tabela() -> None:
    assert {codigo: ISO_ALFA3_POR_CODIGO_SIAPE.get(codigo) for codigo in USADOS_POR_ESTRANGEIROS} == USADOS_POR_ESTRANGEIROS


def test_linhas_decididas_na_curadoria() -> None:
    """Território vai para o Estado emissor; TWN e PSE têm passaporte próprio; ANTILHAS é a única extinta incluída."""
    decididas = {'209': 'FRA', '182': 'CHN', '192': 'NZL', '060': 'TWN', '290': 'PSE', '173': 'NLD', '172': None, '292': None}

    assert {codigo: ISO_ALFA3_POR_CODIGO_SIAPE.get(codigo) for codigo in decididas} == decididas


@pytest.mark.django_db
def test_preenche_vazio_e_nao_sobrescreve_correcao() -> None:
    vazio = Pais.objects.create(codigo='011', nome='ARGENTINA')
    corrigido = Pais.objects.create(codigo='024', nome='BRASIL', iso_alfa3='XYZ')
    extinto = Pais.objects.create(codigo='005', nome='ALEMANHA ORIENTAL')

    call_command('preencher_iso_paises', verbosity=0)

    assert dict(Pais.objects.filter(pk__in=[vazio.pk, corrigido.pk, extinto.pk]).values_list('codigo', 'iso_alfa3')) == {
        '011': 'ARG',
        '024': 'XYZ',
        '005': '',
    }


@pytest.mark.django_db
def test_fixture_de_paises_segue_a_tabela_iso() -> None:
    """A instalação do zero recebe o alfa-3 pela fixture, não pela migration 0121: as duas fontes não podem divergir."""
    call_command('loaddata', 'comum/fixtures/paises.json', verbosity=0)

    paises = Pais.objects.values_list('codigo', 'iso_alfa3')
    assert {codigo: iso for codigo, iso in paises if iso} == ISO_ALFA3_POR_CODIGO_SIAPE
    assert len({codigo for codigo, _ in paises}) == len(paises)


@pytest.mark.parametrize(('iso', 'valido'), [('arg', False), ('AR1', False), ('ARG', True), ('', True)])
def test_iso_alfa3_aceita_so_tres_letras_maiusculas_ou_vazio(iso: str, valido: bool) -> None:
    pais = Pais(codigo='011', nome='ARGENTINA', iso_alfa3=iso)

    if valido:
        pais.full_clean()
    else:
        with pytest.raises(ValidationError) as erro:
            pais.full_clean()
        assert list(erro.value.message_dict) == ['iso_alfa3']
