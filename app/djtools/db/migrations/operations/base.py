import tqdm
from django.db import models
from django.db.migrations.operations.base import Operation
from django.utils.functional import cached_property

from djtools.db.migrations.operations import OperationMixin


class RemoveInheritance(Operation, OperationMixin):
    reduce_to_sql = False
    reversible = False

    def __init__(self, model_name, old_inheritance_pk, new_one_to_one_field_name, new_one_to_one_field, bases=None, prev_bases=None, deferred=True):
        self.model_name = model_name
        self.bases = bases or (models.Model, )
        self.new_one_to_one_field = new_one_to_one_field
        self.new_one_to_one_field_name = new_one_to_one_field_name
        self.old_inheritance_pk = old_inheritance_pk
        self.prev_bases = prev_bases
        self.deferred = deferred

    @cached_property
    def model_name_lower(self):
        return self.model_name.lower()

    def state_forwards(self, app_label, state):
        # Changing inheritance
        state.models[app_label, self.model_name].bases = self.bases

        # Adding AutoField to model
        state.add_field(
            app_label,
            self.model_name_lower,
            'id',
            models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID'),
            True,
        )
        # Removing pointer_id to foreignkey field
        state.remove_field(app_label, self.model_name_lower, self.old_inheritance_pk)
        # Adding new One to One Field
        state.add_field(
            app_label,
            self.model_name_lower,
            self.new_one_to_one_field_name,
            self.new_one_to_one_field,
            True,
        )

    def state_backwards(self, app_label, state):
        state.models[app_label, self.model_name].bases = self.prev_bases
        state.reload_model(app_label, self.model_name)

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        base_column = None
        if not self.deferred:
            schema_editor.execute('SET CONSTRAINTS ALL IMMEDIATE;')
        model = to_state.apps.get_model(app_label, self.model_name)
        base_table = model._meta.db_table
        # Getting related table constraints
        old_related_constraints = self._get_inverted_constraints(schema_editor, base_table)
        # O DROP COLUMN abaixo leva junto os índices e UNIQUE das colunas; guardados para recriar no fim (#17730)
        indices = self._get_indices_das_colunas(schema_editor, [(table, remote_column) for _, table, remote_column, _ in old_related_constraints.values()])
        for constraint, (base_column, table, remote_column, nullable) in old_related_constraints.items():
            # Removing constraints from related tables
            self._delete_constraint(schema_editor, table, constraint)
            # Creating new column for new ids
            self._create_new_fk(schema_editor, table, f'{remote_column}_copy', 'integer')
        # Removing pk from foreignkey
        schema_editor._delete_primary_key(model)
        # Creating id field in model
        schema_editor.add_field(
            model,
            model._meta.get_field('id'),
        )

        # Mapping new pks
        mapped_pks = self._map_pks_values(schema_editor, base_table, base_column, 'id') if base_column else []

        # Saving file with mapped pks for reference
        with open(f'/tmp/{base_table}_{base_column}.txt', 'w') as f:
            f.write('old_fk:new_fk\n')
            f.writelines([str(f'{line[0]}:{line[1]}\n') for line in mapped_pks])

        for constraint, (base_column, table, remote_column, nullable) in tqdm.tqdm(old_related_constraints.items()):
            # Updating with new foreign keys
            for old_fk, new_fk in mapped_pks:
                self._update_fks(schema_editor, table, remote_column, old_fk, new_fk)
            # Removing old columns
            self._remove_column(schema_editor, table, remote_column)
            # Renaming new columns
            self._rename_column(schema_editor, table, f'{remote_column}_copy', remote_column)
            # Adding not null constraint
            if not nullable:
                self._add_not_null(schema_editor, table, remote_column)
            # Recreating fk constraint
            self._create_new_fk_constraint(schema_editor, table, constraint, remote_column, base_table, 'id')
        # Só depois do loop: um índice composto com duas colunas afetadas cairia de novo no 2º DROP
        self._recriar_indices(schema_editor, indices)

        # Destroying constraint for old primary key
        fk_constraint = schema_editor._constraint_names(model, column_names=[f'{self.old_inheritance_pk}_id'])[0]
        self._delete_constraint(schema_editor, base_table, fk_constraint)

        # Getting new one-to-one field model
        new_one_to_one_model = to_state.apps.get_model(self.new_one_to_one_field.related_model)

        # Renaming old foreign key to new one to one field
        new_one_to_one_column = f'{self.new_one_to_one_field_name}_id'
        self._rename_column(schema_editor, base_table, f'{self.old_inheritance_pk}_id', new_one_to_one_column)

        # Recreating fk constraint to new one to one field
        to_table = new_one_to_one_model._meta.db_table
        to_column = new_one_to_one_model._meta.pk.column
        fk_contraint_new_name = f'{to_table}_{to_column}_fkey'
        self._create_new_fk_constraint(schema_editor, base_table, fk_contraint_new_name, new_one_to_one_column, to_table, to_column)

        # Creating Unique constraint for new one to one field
        schema_editor.execute(schema_editor._create_unique_sql(model, [model._meta.get_field(self.new_one_to_one_field_name)]))
        if not self.deferred:
            schema_editor.execute('SET CONSTRAINTS ALL DEFERRED;')

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        pass

    def describe(self):
        return f'Update {self.model_name} bases to {self.bases}'
