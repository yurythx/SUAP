"""Drift de índices/UNIQUE entre o banco e o state (#17730): a migration corretiva e o RemoveInheritance."""

import pytest
from django.apps import apps
from django.db import connection

from djtools.db.migrations.indices import recriar_indices_e_unicidades
from djtools.db.migrations.operations import OperationMixin

pytestmark = pytest.mark.django_db


def _indices(tabela: str) -> list[tuple[str, list[str], bool]]:
    """(nome, colunas na ordem, único) de cada índice da tabela."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
                SELECT ci.relname, array_agg(a.attname ORDER BY k.ordem), i.indisunique
                FROM pg_index i
                JOIN pg_class ci ON ci.oid = i.indexrelid
                CROSS JOIN LATERAL unnest(i.indkey::int2[]) WITH ORDINALITY AS k(attnum, ordem)
                JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = k.attnum
                WHERE i.indrelid = %s::regclass
                GROUP BY ci.relname, i.indisunique
            """,
            [tabela],
        )
        return [(nome, list(colunas), unico) for nome, colunas, unico in cursor.fetchall()]


def _constraints_unique(tabela: str) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT conname FROM pg_constraint WHERE conrelid = %s::regclass AND contype = 'u'", [tabela])
        return {nome for (nome,) in cursor.fetchall()}


def _derrubar(tabela: str, colunas_iniciais: str) -> None:
    """Simula o drift: remove todo índice/UNIQUE da tabela que comece pela coluna."""
    for nome, colunas, _ in _indices(tabela):
        if colunas[0] == colunas_iniciais:
            with connection.cursor() as cursor:
                if nome in _constraints_unique(tabela):
                    cursor.execute(f'ALTER TABLE {tabela} DROP CONSTRAINT {nome}')
                else:
                    cursor.execute(f'DROP INDEX {nome}')


def test_recria_unique_e_indice_de_fk_que_faltam_sem_duplicar_ao_rodar_de_novo():
    _derrubar('ferias_ferias', 'servidor_id')
    assert not any(colunas[0] == 'servidor_id' for _, colunas, _ in _indices('ferias_ferias'))

    with connection.schema_editor() as editor:
        recriar_indices_e_unicidades(apps.get_app_config('ferias'), editor)

    # unique_together (servidor, ano) volta como constraint, e já cobre a FK servidor_id
    assert any(
        set(colunas) == {'servidor_id', 'ano_id'} and nome in _constraints_unique('ferias_ferias') for nome, colunas, _ in _indices('ferias_ferias')
    )
    antes = _indices('ferias_ferias')
    with connection.schema_editor() as editor:
        recriar_indices_e_unicidades(apps.get_app_config('ferias'), editor)
    assert sorted(_indices('ferias_ferias')) == sorted(antes)


def test_unique_com_duplicata_e_pulada_sem_abortar(capsys):
    _derrubar('comum_ano', 'ano')
    with connection.cursor() as cursor:
        cursor.execute('INSERT INTO comum_ano (ano) VALUES (1901), (1901)')

    with connection.schema_editor() as editor:
        recriar_indices_e_unicidades(apps.get_app_config('comum'), editor)

    assert not any(colunas == ['ano'] for _, colunas, _ in _indices('comum_ano'))
    assert 'Pulado comum_ano (ano)' in capsys.readouterr().out
    with connection.cursor() as cursor:  # a transação segue utilizável
        cursor.execute('SELECT count(*) FROM comum_ano WHERE ano = 1901')
        assert cursor.fetchone()[0] == 2


def test_troca_de_coluna_do_remove_inheritance_preserva_indices_e_unique():
    with connection.cursor() as cursor:
        cursor.execute('CREATE TABLE t_heranca (id serial PRIMARY KEY, a int, b int)')
        cursor.execute('CREATE INDEX t_heranca_a ON t_heranca (a)')
        cursor.execute('ALTER TABLE t_heranca ADD CONSTRAINT t_heranca_a_b_uniq UNIQUE (a, b)')
    antes = sorted(_indices('t_heranca'))
    operacao = OperationMixin()

    with connection.schema_editor() as editor:
        definicoes = operacao._get_indices_das_colunas(editor, [('t_heranca', 'a'), ('t_heranca', 'b')])
        # Mesma sequência do RemoveInheritance.database_forwards para cada FK que aponta para o model
        for coluna in ('a', 'b'):
            operacao._create_new_fk(editor, 't_heranca', f'{coluna}_copy', 'integer')
            operacao._remove_column(editor, 't_heranca', coluna)
            operacao._rename_column(editor, 't_heranca', f'{coluna}_copy', coluna)
        operacao._recriar_indices(editor, definicoes)

    assert sorted(_indices('t_heranca')) == antes
    assert _constraints_unique('t_heranca') == {'t_heranca_a_b_uniq'}
