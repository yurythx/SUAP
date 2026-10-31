"""Recria no banco os índices de FK e as UNIQUE que o state das migrations declara e que faltam (#17730).

O drift tem duas origens: o reset de migrations de 2019, aplicado com `--fake` sobre o schema
legado, e o `RemoveInheritance`, que derrubava índices e UNIQUE das FKs que apontavam para o
model. Idempotente: só cria o que falta, então pode rodar de novo sem efeito.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import nullcontext

from django.db import DatabaseError, transaction
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.models import Field, Model, UniqueConstraint
from django.db.models.options import Options

# Colunas (na ordem do índice) e se é único, de cada índice válido e não parcial da tabela.
# Coluna de expressão vira None, para não casar com nenhuma FK.
SQL_INDICES_DA_TABELA = """
    SELECT array_agg(a.attname ORDER BY k.ordem), i.indisunique
    FROM pg_index i
    CROSS JOIN LATERAL unnest(i.indkey::int2[]) WITH ORDINALITY AS k(attnum, ordem)
    LEFT JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = k.attnum
    WHERE i.indrelid = %s::regclass AND i.indisvalid AND i.indpred IS NULL
    GROUP BY i.indexrelid, i.indisunique
"""

Indice = tuple[tuple[str | None, ...], bool]


def recriar_indices_e_unicidades(apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    """Função do `RunPython`: alinha, model a model, as UNIQUE e os índices de FK ao state."""
    for model in apps.get_models(include_auto_created=True):
        if model._meta.managed and not model._meta.proxy:
            _alinhar_model(schema_editor, model)


def _alinhar_model(schema_editor: BaseDatabaseSchemaEditor, model: type[Model]) -> None:
    tabela = model._meta.db_table
    indices = _indices_da_tabela(schema_editor, tabela)
    if indices is None:
        return
    # UNIQUE antes das FKs: numa M2M, a UNIQUE (a, b) já serve de índice para `a`.
    for colunas, nome in _unicidades(schema_editor, model):
        if not any(unico and set(cols) == set(colunas) for cols, unico in indices):
            if _criar_indice(schema_editor, tabela, nome, colunas, unico=True):
                indices.append((tuple(colunas), True))
    for coluna in _colunas_fk_indexadas(model):
        if not any(cols[0] == coluna for cols, _ in indices):
            if _criar_indice(schema_editor, tabela, _nome_django(schema_editor, tabela, [coluna]), [coluna], unico=False):
                indices.append(((coluna,), False))


def _indices_da_tabela(schema_editor: BaseDatabaseSchemaEditor, tabela: str) -> list[Indice] | None:
    """Índices existentes da tabela, ou None se a tabela não existe neste banco."""
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('SELECT to_regclass(%s)', [tabela])
        if cursor.fetchone()[0] is None:
            return None
        cursor.execute(SQL_INDICES_DA_TABELA, [tabela])
        return [(tuple(colunas), unico) for colunas, unico in cursor.fetchall()]


def _unicidades(schema_editor: BaseDatabaseSchemaEditor, model: type[Model]) -> Iterator[tuple[list[str], str]]:
    """(colunas, nome) de cada UNIQUE declarada: campo unique, unique_together e UniqueConstraint simples."""
    opts = model._meta
    tabela = opts.db_table
    for campos in opts.unique_together:
        colunas = [_coluna(opts, campo) for campo in campos]
        yield colunas, _nome_django(schema_editor, tabela, colunas, '_uniq')
    for campo in opts.local_fields:
        if campo.unique and not campo.primary_key:
            colunas = [_coluna(opts, campo.name)]
            yield colunas, _nome_django(schema_editor, tabela, colunas, '_uniq')
    for constraint in opts.constraints:
        if isinstance(constraint, UniqueConstraint) and constraint.fields and not _tem_extras(constraint):
            yield [_coluna(opts, campo) for campo in constraint.fields], constraint.name


def _tem_extras(constraint: UniqueConstraint) -> bool:
    """Condição, expressão, INCLUDE ou opclass: não dá para comparar só pelas colunas."""
    return bool(constraint.condition or constraint.expressions or constraint.include or constraint.opclasses)  # pyright: ignore[reportAttributeAccessIssue]  # include/opclasses faltam nos stubs


def _colunas_fk_indexadas(model: type[Model]) -> Iterator[str]:
    for campo in model._meta.local_fields:
        if campo.many_to_one and campo.db_index and not campo.unique:  # pyright: ignore[reportAttributeAccessIssue]  # db_index falta nos stubs
            yield _coluna(model._meta, campo.name)


def _coluna(opts: Options, campo: str) -> str:
    field = opts.get_field(campo)
    assert isinstance(field, Field)
    return str(field.column)


def _nome_django(schema_editor: BaseDatabaseSchemaEditor, tabela: str, colunas: list[str], sufixo: str = '') -> str:
    """O nome que o próprio Django daria (o mesmo do banco criado por migrations); API privada, fora dos stubs."""
    return schema_editor._create_index_name(tabela, colunas, suffix=sufixo)  # pyright: ignore[reportAttributeAccessIssue]


def _criar_indice(schema_editor: BaseDatabaseSchemaEditor, tabela: str, nome: str, colunas: list[str], unico: bool) -> bool:
    """Cria o índice (e a constraint, se único); em falha, desfaz, avisa e segue.

    Falha esperada: duplicata já gravada impede a UNIQUE. Deduplicar é decisão de dado,
    fora desta migration; rodá-la de novo depois da limpeza cria o que faltou.
    """
    conexao = schema_editor.connection
    q = schema_editor.quote_name
    # Fora de transação (deploy) usa CONCURRENTLY para não bloquear escrita; em teste, não pode.
    concorrente = '' if conexao.in_atomic_block else ' CONCURRENTLY'
    sql = f'CREATE {"UNIQUE " if unico else ""}INDEX{concorrente} {q(nome)} ON {q(tabela)} ({", ".join(map(q, colunas))})'
    savepoint = transaction.atomic(using=conexao.alias) if conexao.in_atomic_block else nullcontext()
    try:
        with savepoint:
            schema_editor.execute(sql, params=None)
            if unico:
                _anexar_constraint(schema_editor, tabela, nome)
    except DatabaseError as erro:
        sys.stdout.write(f'\n  Pulado {tabela} ({", ".join(colunas)}): {str(erro).strip().splitlines()[0]}')
        if not conexao.in_atomic_block:
            # CONCURRENTLY que falha deixa índice INVALID com o nome; sem isso, a próxima rodada o pularia.
            schema_editor.execute(f'DROP INDEX{concorrente} IF EXISTS {q(nome)}', params=None)
        return False
    return True


def _anexar_constraint(schema_editor: BaseDatabaseSchemaEditor, tabela: str, nome: str) -> None:
    """Promove o índice único a constraint, como o Django cria; senão a remoção futura por migration falha.

    Pega ACCESS EXCLUSIVE só pelo instante da troca. `SET LOCAL` fica preso à transação, o que
    também o mantém na mesma conexão de servidor sob o pgbouncer em modo transaction.
    """
    q = schema_editor.quote_name
    with transaction.atomic(using=schema_editor.connection.alias):
        schema_editor.execute("SET LOCAL lock_timeout = '5s'", params=None)
        schema_editor.execute(f'ALTER TABLE {q(tabela)} ADD CONSTRAINT {q(nome)} UNIQUE USING INDEX {q(nome)}', params=None)
