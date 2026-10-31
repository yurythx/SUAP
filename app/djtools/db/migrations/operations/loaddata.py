import json
import os
import logging

from django.core import serializers
from django.core.management.color import no_style
from django.core.management.base import CommandError
from django.db import (
    DEFAULT_DB_ALIAS,
    DatabaseError,
    IntegrityError,
    models,
)

from django.db.migrations.operations.base import Operation

from djtools.db.migrations.operations import OperationMixin

logger = logging.getLogger(__name__)

class RunLoadData(Operation, OperationMixin):
    reduce_to_sql = False
    reversible = True

    def __init__(self, file_name):
        self.file_name = file_name

    def state_forwards(self, app_label, state):
        pass

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        self.loaddata(self.file_name, schema_editor.connection, to_state)

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        pass

    def loaddata(self, fixture_name, connection, state):

        # Keep a count of the installed objects and fixtures
        self.fixture_count = 0
        self.loaded_object_count = 0
        self.fixture_object_count = 0
        self.models = set()

        self.serialization_formats = serializers.get_public_serializer_formats()

        self.objs_with_deferred_fields = []
        with connection.constraint_checks_disabled():
            self.load_label(fixture_name, state)
            for obj in self.objs_with_deferred_fields:
                obj.save_deferred_fields()

        # Since we disabled constraint checks, we must manually check for
        # any invalid keys that might have been added
        table_names = [model._meta.db_table for model in self.models]
        try:
            connection.check_constraints(table_names=table_names)
        except Exception as e:
            e.args = ("Problem installing fixtures: %s" % e,)
            raise

        # If we found even one object in a fixture, we need to reset the
        # database sequences.
        if self.loaded_object_count > 0:
            self.reset_sequences(connection, self.models)

        if self.fixture_object_count == self.loaded_object_count:
            logger.info(
                "Installed %d object(s) from %d fixture(s)"
                % (self.loaded_object_count, self.fixture_count)
            )
        else:
            logger.info(
                "Installed %d object(s) (of %d)"
                % (
                    self.loaded_object_count,
                    self.fixture_object_count,
                )
            )

    def reset_sequences(self, connection, models):
        """Reset database sequences for the given connection and models."""
        sequence_sql = connection.ops.sequence_reset_sql(no_style(), models)
        if sequence_sql:
            logger.info("Resetting sequences")
            with connection.cursor() as cursor:
                for line in sequence_sql:
                    cursor.execute(line)

    def save_obj(self, obj):
        """Save an object if permitted."""
        self.models.add(obj.object.__class__)
        try:
            obj.save()
            saved = True
        # psycopg raises ValueError if data contains NUL chars.
        except (DatabaseError, IntegrityError, ValueError) as e:
            e.args = (
                "Could not load %(object_label)s(pk=%(pk)s): %(error_msg)s"
                % {
                    "object_label": obj.object._meta.label,
                    "pk": obj.object.pk,
                    "error_msg": e,
                },
            )
            raise
        if obj.deferred_fields:
            self.objs_with_deferred_fields.append(obj)
        return saved

    def load_label(self, fixture_file, state):
        """Load fixtures files for a given label."""

        fixture = open(fixture_file, 'rb')
        content = fixture.read()
        objects_in_fixture = 0
        loaded_objects_in_fixture = 0
        logger.info(
            "Installing json fixture '%s'"
            % (fixture_file)
        )
        try:
            dict_objects = json.loads(content)
            objects = deserialize(
                state,
                dict_objects,
                handle_forward_references=True,
            )

            for obj in objects:
                objects_in_fixture += 1
                if self.save_obj(obj):
                    loaded_objects_in_fixture += 1
            logger.info(
                "Processed %i object(s)." % loaded_objects_in_fixture,
            )
        except Exception as e:
            if not isinstance(e, CommandError):
                e.args = (
                    f"Problem installing fixture '{fixture_file}': {e}",
                )
            raise
        finally:
            fixture.close()

        if objects_in_fixture:
            logger.info("Processed %i object(s)." % objects_in_fixture)  # Add a newline after progress indicator.
        self.loaded_object_count += loaded_objects_in_fixture
        self.fixture_object_count += objects_in_fixture
        # Warn if the fixture we loaded contains 0 objects.
        if objects_in_fixture == 0:
            logger.warning(
                "No fixture data found for '%s'. (File format may be "
                "invalid.)" % fixture_file,
            )

    def get_fixture_name_and_dirs(self, fixture_name):
        dirname, basename = os.path.split(fixture_name)
        return basename, [dirname]


def deserialize(
    state, object_list, *args, **options
):
    """
    Deserialize simple Python objects back into Django ORM instances.

    It's expected that you pass the Python objects themselves (instead of a
    stream or a string) to the constructor
    """
    handle_forward_references = options.pop("handle_forward_references", False)
    field_names_cache = {}  # Model: <list of field_names>
    using = DEFAULT_DB_ALIAS

    for d in object_list:
        # Look up the model and starting build a dict of data for it.
        Model = _get_model(state, d["model"])
        data = {}
        if "pk" in d:
            try:
                data[Model._meta.pk.attname] = Model._meta.pk.to_python(d.get("pk"))
            except Exception as e:
                raise serializers.base.DeserializationError.WithData(
                    e, d["model"], d.get("pk"), None
                )
        m2m_data = {}
        deferred_fields = {}

        if Model not in field_names_cache:
            field_names_cache[Model] = {f.name for f in Model._meta.get_fields()}
        field_names = field_names_cache[Model]

        # Handle each field
        for field_name, field_value in d["fields"].items():
            if field_name not in field_names:
                # skip fields no longer on model
                continue

            field = Model._meta.get_field(field_name)

            # Handle M2M relations
            if field.remote_field and isinstance(
                field.remote_field, models.ManyToManyRel
            ):
                try:
                    values = serializers.base.deserialize_m2m_values(
                        field, field_value, using, handle_forward_references
                    )
                except serializers.base.M2MDeserializationError as e:
                    raise serializers.base.DeserializationError.WithData(
                        e.original_exc, d["model"], d.get("pk"), e.pk
                    )
                if values == serializers.base.DEFER_FIELD:
                    deferred_fields[field] = field_value
                else:
                    m2m_data[field.name] = values
            # Handle FK fields
            elif field.remote_field and isinstance(
                field.remote_field, models.ManyToOneRel
            ):
                try:
                    value = serializers.base.deserialize_fk_value(
                        field, field_value, using, handle_forward_references
                    )
                except Exception as e:
                    raise serializers.base.DeserializationError.WithData(
                        e, d["model"], d.get("pk"), field_value
                    )
                if value == serializers.base.DEFER_FIELD:
                    deferred_fields[field] = field_value
                else:
                    data[field.attname] = value
            # Handle all other fields
            else:
                try:
                    data[field.name] = field.to_python(field_value)
                except Exception as e:
                    raise serializers.base.DeserializationError.WithData(
                        e, d["model"], d.get("pk"), field_value
                    )

        obj = serializers.base.build_instance(Model, data, using)
        yield serializers.base.DeserializedObject(obj, m2m_data, deferred_fields)


def _get_model(state, model_identifier):
    """Look up a model from an "app_label.model_name" string."""
    try:
        return state.apps.get_model(model_identifier)
    except (LookupError, TypeError):
        raise serializers.base.DeserializationError(
            "Identificador de modelo inválido: '%s'" % model_identifier
        )
