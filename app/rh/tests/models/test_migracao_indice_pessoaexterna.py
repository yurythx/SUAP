"""rh/0109: índice da FK rh_pessoaexterna.pessoa_fisica_id, criado só onde falta."""

import importlib

import pytest
from django.db import connection

pytestmark = pytest.mark.django_db
migracao = importlib.import_module('rh.migrations.0109_indice_pessoaexterna_pessoa_fisica')


def _indices_da_fk() -> list[str]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT indexname FROM pg_indexes WHERE tablename = 'rh_pessoaexterna' AND indexdef LIKE '%(pessoa_fisica_id%' ORDER BY 1")
        return [nome for (nome,) in cursor.fetchall()]


def _migrar() -> None:
    with connection.cursor() as cursor:
        for operacao in migracao.Migration.operations:
            cursor.execute(operacao.sql)


def _apagar_indices_da_fk() -> None:
    with connection.cursor() as cursor:
        for nome in _indices_da_fk():
            cursor.execute(f'DROP INDEX {connection.ops.quote_name(nome)}')


def test_nome_e_o_que_o_django_da_ao_indice_da_fk() -> None:
    with connection.schema_editor() as editor:
        assert editor._create_index_name('rh_pessoaexterna', ['pessoa_fisica_id']) == migracao.INDICE


def test_banco_sem_o_indice_ganha_o_indice_e_migrar_de_novo_nao_duplica() -> None:
    _apagar_indices_da_fk()

    _migrar()
    _migrar()

    assert _indices_da_fk() == [migracao.INDICE]


def test_indice_existente_com_outro_nome_nao_ganha_outro() -> None:
    _apagar_indices_da_fk()
    with connection.cursor() as cursor:
        cursor.execute('CREATE INDEX indice_local_da_instituicao ON rh_pessoaexterna (pessoa_fisica_id, id)')

    _migrar()

    assert _indices_da_fk() == ['indice_local_da_instituicao']


def test_indice_parcial_nao_conta_e_a_fk_ganha_o_indice_completo() -> None:
    _apagar_indices_da_fk()
    with connection.cursor() as cursor:
        cursor.execute('CREATE INDEX indice_parcial ON rh_pessoaexterna (pessoa_fisica_id) WHERE cpf IS NOT NULL')

    _migrar()

    assert _indices_da_fk() == ['indice_parcial', migracao.INDICE]
