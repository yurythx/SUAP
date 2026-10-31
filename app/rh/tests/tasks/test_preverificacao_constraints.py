import pytest
from django.db import connection

from comum.models import APIExterna, Pais
from rh.deduplicacao.verificacao import pendencias
from rh.models import DeduplicacaoPessoa, PessoaFisica, PessoaInfoComplementar
from rh.tests.factories import PessoaFisicaFactory

pytestmark = pytest.mark.usefixtures('sem_unicidade_pessoa')


def _pendencias() -> dict[str, int]:
    with connection.cursor() as cursor:
        return {chave: total for chave, total in pendencias(cursor).items() if total}


def test_base_deduplicada_nao_tem_pendencia() -> None:
    PessoaFisicaFactory(), PessoaFisicaFactory()

    assert _pendencias() == {}


def test_aponta_cada_tipo_de_pendencia() -> None:
    PessoaFisicaFactory(cpf='529.982.247-25'), PessoaFisicaFactory(cpf='529.982.247-25')
    sem = PessoaFisicaFactory()
    PessoaFisica.objects.filter(pk=sem.pk).update(cpf=None, documento_identificador=None)
    DeduplicacaoPessoa.objects.create(pf_id=1, acao=DeduplicacaoPessoa.ERRO)

    assert _pendencias() == {'cpf_repetido': 1, 'documento_repetido': 1, 'sem_documento': 1, 'deduplicacao_pendente': 1}


def test_sem_cpf_e_sem_pais_so_passa_com_sintetico() -> None:
    sintetica, sem_pais = PessoaFisicaFactory(), PessoaFisicaFactory()
    PessoaFisica.objects.filter(pk=sintetica.pk).update(cpf=None, documento_identificador='SEMDOC-1')
    PessoaFisica.objects.filter(pk=sem_pais.pk).update(cpf=None, passaporte='AB123456', documento_identificador='AB123456')

    assert _pendencias() == {'sem_cpf_sem_pais': 1}


def test_passaporte_repetido_no_mesmo_pais() -> None:
    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA')
    PessoaFisicaFactory(passaporte='AB123456', pais_origem=argentina), PessoaFisicaFactory(passaporte='AB123456', pais_origem=argentina)

    assert _pendencias() == {'passaporte_repetido': 1}


def test_cpf_ou_passaporte_vazio() -> None:
    cpf_vazio, passaporte_vazio = PessoaFisicaFactory(), PessoaFisicaFactory()
    PessoaFisica.objects.filter(pk=cpf_vazio.pk).update(cpf='')
    PessoaFisica.objects.filter(pk=passaporte_vazio.pk).update(passaporte='')

    assert _pendencias() == {'cpf_ou_passaporte_vazio': 2}


def test_campo_descartado_nao_e_pendencia() -> None:
    DeduplicacaoPessoa.objects.create(pf_id=1, acao=DeduplicacaoPessoa.CAMPO_DESCARTADO)

    assert _pendencias() == {}


def test_info_complementar_repetida() -> None:
    api = APIExterna.objects.create(
        nome='API de teste', url_base='https://api.teste', tipo_autenticacao=APIExterna.TOKEN_AUTH, client_id='id', secret='segredo'
    )
    pessoa = PessoaFisicaFactory()
    PessoaInfoComplementar.objects.create(pessoa=pessoa, api_origem=api, informacoes={})
    PessoaInfoComplementar.objects.create(pessoa=pessoa, api_origem=api, informacoes={})

    assert _pendencias() == {'info_complementar_repetida': 1}
