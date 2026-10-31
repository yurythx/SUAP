from collections.abc import Iterable

from django.db.backends.ddl_references import Statement, Table


class OperationMixin:
    def _get_inverted_constraints(self, schema_editor, table_name):
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(
                '''
                    select constraints.*,
                           case columns.is_nullable
                                when 'NO' then false
                                when 'YES' then true
                        end as nullable
                    FROM information_schema.columns as columns INNER JOIN (SELECT
                           c.conname as constraint_name,
                           a.attname as base_col,
                           (select r.relname from pg_class r where r.oid = c.conrelid) as referencing_table,
                           UNNEST((select array_agg(attname) from pg_attribute where attrelid = c.conrelid and array[attnum] <@ c.conkey)) as referencing_col
                      FROM pg_constraint c join pg_attribute a on c.confrelid=a.attrelid and a.attnum = ANY(confkey)
                     WHERE c.confrelid = (select oid from pg_class where relname = %s)
                       AND c.confrelid!=c.conrelid) as constraints ON columns.column_name = constraints.referencing_col and columns.table_name = constraints.referencing_table
                ''',
                [table_name],
            )
            result = {row[0]: (row[1], row[2], row[3], row[4]) for row in cursor.fetchall()}
            return result

    def _get_indices_das_colunas(self, schema_editor, colunas: Iterable[tuple[str, str]]) -> dict[str, tuple[str, str, str | None, str | None]]:
        """Definição de cada índice (e constraint UNIQUE/PK) que usa alguma das colunas (tabela, coluna).

        O DROP COLUMN derruba esses objetos; capturá-los antes permite recriá-los depois do rename.
        A chave é o nome do índice: um índice que cubra duas colunas afetadas é recriado uma vez só.
        """
        definicoes = {}
        with schema_editor.connection.cursor() as cursor:
            for tabela, coluna in colunas:
                cursor.execute(
                    '''
                        SELECT ci.relname, pg_get_indexdef(i.indexrelid), c.conname, pg_get_constraintdef(c.oid)
                        FROM pg_index i
                        JOIN pg_class ci ON ci.oid = i.indexrelid
                        JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                        LEFT JOIN pg_constraint c ON c.conindid = i.indexrelid AND c.contype IN ('u', 'p')
                        WHERE i.indrelid = %s::regclass AND a.attname = %s
                    ''',
                    [tabela, coluna],
                )
                for nome, indexdef, conname, condef in cursor.fetchall():
                    definicoes[nome] = (tabela, indexdef, conname, condef)
        return definicoes

    def _recriar_indices(self, schema_editor, definicoes: dict[str, tuple[str, str, str | None, str | None]]) -> None:
        q = schema_editor.quote_name
        for tabela, indexdef, conname, condef in definicoes.values():
            sql = f'ALTER TABLE {q(tabela)} ADD CONSTRAINT {q(conname)} {condef}' if conname else indexdef
            schema_editor.execute(sql, params=None)

    def _statement_sql_table(self, schema_editor, template, table_name, column):
        return Statement(
            template,
            table=Table(table_name, schema_editor.quote_name),
            name=schema_editor.quote_name(column),
        )

    def _delete_constraint(self, schema_editor, table_name, constraint):
        template = schema_editor.sql_delete_constraint
        return schema_editor.execute(self._statement_sql_table(schema_editor, template, table_name, constraint))

    def _create_new_fk(self, schema_editor, table_name, column, definition):
        # Build the SQL and run it
        sql = schema_editor.sql_create_column % {
            'table': schema_editor.quote_name(table_name),
            'column': schema_editor.quote_name(column),
            'definition': definition,
        }
        schema_editor.execute(sql)

    def _create_new_fk_constraint(self, schema_editor, table_name, name, column, to_table, to_column):
        sql = schema_editor.sql_create_fk % {
            'table': schema_editor.quote_name(table_name),
            'name': name,
            'column': schema_editor.quote_name(column),
            'to_table': schema_editor.quote_name(to_table),
            'to_column': schema_editor.quote_name(to_column),
            'deferrable': ' DEFERRABLE INITIALLY DEFERRED'
        }
        schema_editor.execute(sql)

    def _map_pks_values(self, schema_editor, table_name, old_fk, new_fk):
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(
                f'SELECT {old_fk}, {new_fk} FROM {table_name}'
            )
            return cursor.fetchall()

    def _update_fks(self, schema_editor, table_name, column, old_fk, new_fk):
        schema_editor.execute(
            f'UPDATE {table_name} SET {column}_copy = {new_fk} WHERE {column} = {old_fk}'
        )

    def _remove_column(self, schema_editor, table_name, column):
        sql = schema_editor.sql_delete_column % {
            'table': table_name,
            'column': column,
        }
        try:
            schema_editor.execute(sql)
        except Exception:
            raise Exception(f'Tabela {table_name} - coluna: {column} não pode ser excluida, defina o deferred para False na migration RemoveInheritance.')

    def _rename_column(self, schema_editor, table_name, old_column, new_column):
        sql = schema_editor.sql_rename_column % {
            'table': table_name,
            'old_column': old_column,
            'new_column': new_column
        }
        schema_editor.execute(sql)

    def _add_not_null(self, schema_editor, table_name, column):
        changes_sql = schema_editor.sql_alter_column_not_null % {
            'column': column
        }
        sql = schema_editor.sql_alter_column % {
            'table': table_name,
            'changes': changes_sql,
        }
        schema_editor.execute(sql)
