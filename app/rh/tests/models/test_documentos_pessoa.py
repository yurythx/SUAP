import pytest

from rh.deduplicacao.documentos import (
    chave_passaporte,
    cpf_valido,
    documento_sintetico,
    eh_sintetico,
    formatar_cpf,
    formatar_passaporte,
    normalizar_nome_pais,
    passaporte_valido,
)


@pytest.mark.parametrize(
    ('entrada', 'esperado'),
    [
        ('52998224725', '529.982.247-25'),
        ('529.982.247-25', '529.982.247-25'),
        ('529 982 247 25', '529.982.247-25'),
        ('___.___.___-__', None),
        ('-', None),
        ('', None),
        (None, None),
        (' 1234 ', '1234'),
    ],
)
def test_formatar_cpf_so_formata(entrada: str | None, esperado: str | None) -> None:
    assert formatar_cpf(entrada) == esperado


@pytest.mark.parametrize(
    ('entrada', 'esperado'),
    [
        ('529.982.247-25', True),
        ('52998224725', True),
        ('529.982.247-24', False),
        ('111.111.111-11', False),
        ('000.000.000-00', False),
        ('1234', False),
        (None, False),
    ],
)
def test_cpf_valido(entrada: str | None, esperado: bool) -> None:
    assert cpf_valido(entrada) is esperado


@pytest.mark.parametrize(
    ('entrada', 'esperado'),
    [(' ab 123456 ', 'AB123456'), ('ab-123.456', 'AB123456'), ('Ñ1234ß5', '12345'), ('', None), ('   ', None), (' -./ ', None), (None, None)],
)
def test_formatar_passaporte(entrada: str | None, esperado: str | None) -> None:
    assert formatar_passaporte(entrada) == esperado


@pytest.mark.parametrize(
    ('entrada', 'esperado'),
    [
        ('AB123456', True),
        ('ab 123456', True),
        ('X', False),
        ('AAAAAA', False),
        ('1234', False),
        (None, False),
        # texto de recusa digitado no campo: sem dígito não é passaporte (todo passaporte tem número)
        ('NÃO TENHO', False),
        ('não possuo passaporte', False),
        ('SEM PASSAPORTE', False),
        # a chave ARG-<passaporte> é o login e tem de caber nos 30 caracteres da matrícula
        ('A' + '1' * 25, True),
        ('A' + '1' * 26, False),
    ],
)
def test_passaporte_valido(entrada: str | None, esperado: bool) -> None:
    assert passaporte_valido(entrada) is esperado


def test_documento_sintetico_guarda_o_documento_original() -> None:
    assert documento_sintetico(7) == 'SEMDOC-7'
    assert documento_sintetico(7, conflito='529.982.247-25') == 'CONFLITO-7-529.982.247-25'
    assert documento_sintetico(7, cpf_invalido='529.982.247-24') == 'INVALIDO-7-52998224724'
    assert documento_sintetico(7, cpf_invalido='___.___.___-__') == 'SEMDOC-7'
    assert documento_sintetico(7, passaporte_sem_pais='ab-123.456') == 'SEMPAIS-7-AB123456'
    assert documento_sintetico(7, passaporte_sem_pais='NÃO TENHO') == 'SEMDOC-7'


def test_chave_passaporte_exige_pais() -> None:
    assert chave_passaporte(' ab 123456 ', 'ARG') == 'ARG-AB123456'
    assert chave_passaporte('AB123456', None) is None
    assert chave_passaporte(None, 'ARG') is None


def test_normalizar_nome_pais() -> None:
    assert normalizar_nome_pais(' Itália ') == 'ITALIA'
    assert normalizar_nome_pais(None) == ''


def test_eh_sintetico() -> None:
    assert eh_sintetico('CONFLITO-1-529.982.247-25')
    assert eh_sintetico('SEMDOC-1')
    assert eh_sintetico('SEMPAIS-1-AB123456')
    assert eh_sintetico('INVALIDO-1-123')
    assert not eh_sintetico('529.982.247-25')
    assert not eh_sintetico(None)


@pytest.mark.django_db
def test_pais_por_nome_ignora_acento_e_caixa() -> None:
    from comum.models import Pais
    from rh.deduplicacao.paises import pais_por_nome

    italia = Pais.objects.create(codigo='386', nome='ITALIA')

    assert pais_por_nome('Itália') == italia
    assert pais_por_nome('Atlântida') is None
