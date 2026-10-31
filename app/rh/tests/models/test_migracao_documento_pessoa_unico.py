"""rh/0111: constraints de documento de PessoaFisica, atrás da trava que exige a deduplicação feita."""

import importlib
from types import SimpleNamespace

import pytest
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from pytest_django.fixtures import Settings

from rh.tests.factories import PessoaFisicaFactory

migracao = importlib.import_module('rh.migrations.0111_documento_pessoa_unico')
FANTASMAS = [
    ('ae', '0047_remover_fantasmas_pessoa'),
    ('cnpq', '0010_remover_fantasmas_pessoa'),
    ('convenios', '0007_remover_fantasmas_pessoa'),
    ('documento_eletronico', '0041_remover_fantasmas_pessoa'),
    ('edu', '0330_remover_fantasmas_pessoa'),
    ('estacionamento', '0003_remover_fantasmas_pessoa'),
    ('frota', '0008_remover_fantasmas_pessoa'),
    ('pesquisa', '0089_remover_fantasmas_pessoa'),
    ('ponto', '0026_remover_fantasmas_pessoa'),
    ('processo_eletronico', '0050_remover_fantasmas_pessoa'),
    ('projetos', '0075_remover_fantasmas_pessoa'),
    ('saude', '0039_remover_fantasmas_pessoa'),
]


def _verificar() -> None:
    migracao.verificar_deduplicacao(None, SimpleNamespace(connection=connection))


def test_fantasmas_e_0109_sao_aplicadas_antes(settings: Settings) -> None:
    settings.MIGRATION_MODULES = {}  # o --no-migrations do pytest esconde as migrations
    plano = MigrationLoader(None, ignore_no_migrations=True).graph.forwards_plan(('rh', '0111_documento_pessoa_unico'))

    assert [no for no in [*FANTASMAS, ('rh', '0109_indice_pessoaexterna_pessoa_fisica')] if no not in plano] == []


@pytest.mark.usefixtures('sem_unicidade_pessoa')
def test_trava_recusa_base_com_duplicata() -> None:
    PessoaFisicaFactory(cpf='529.982.247-25'), PessoaFisicaFactory(cpf='529.982.247-25')

    with pytest.raises(RuntimeError) as erro:
        _verificar()

    assert str(erro.value) == (
        'Deduplicação de pessoas pendente (cpf_repetido=1, documento_repetido=1). O SUAP 4.0.0 exige a deduplicação feita '
        '(introduzida na 3.21.0): rode `python manage.py deduplicar_pessoas planejar`, `relatorio` e `aplicar` e repita o migrate. '
        'Roteiro: docs/operacoes/deduplicar-pessoas.md, seção "Instalou a Release 2 sem ter deduplicado".'
    )


@pytest.mark.django_db
def test_trava_deixa_passar_base_deduplicada() -> None:
    PessoaFisicaFactory(), PessoaFisicaFactory()

    _verificar()
