#!/usr/bin/env bash
set -eu
export PATH="/venv/bin:${PATH:-}"
export PYTHONUNBUFFERED=1
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-suap.settings}"
cd /opt/suap
python - <<'PY'
import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "suap.settings")
django.setup()
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.operations.special import RunPython
from django.db.utils import InternalError, OperationalError, ProgrammingError

with connection.cursor() as c:
    c.execute("DROP SCHEMA public CASCADE")
    c.execute("CREATE SCHEMA public AUTHORIZATION CURRENT_USER")
    c.execute("GRANT ALL ON SCHEMA public TO public")
for s in [
    "CREATE EXTENSION IF NOT EXISTS unaccent",
    "CREATE EXTENSION IF NOT EXISTS pg_trgm",
    "CREATE EXTENSION IF NOT EXISTS pg_stat_statements",
    "CREATE COLLATION IF NOT EXISTS ignore_accents_case (provider='icu', locale='pt-BR-u-ks-level1', deterministic=false)",
    "CREATE OR REPLACE FUNCTION f_unaccent(text) RETURNS text AS $func$ SELECT unaccent('unaccent', upper($1)) $func$ LANGUAGE sql IMMUTABLE SET search_path=public, pg_temp",
]:
    with connection.cursor() as c:
        c.execute(s)

RunPython.database_forwards = lambda *a, **k: None
RunPython.database_backwards = lambda *a, **k: None

for round_i in range(1, 500):
    print(f"==== round {round_i} ====", flush=True)
    try:
        call_command("migrate", interactive=False, verbosity=1)
        print("MIGRATE_SCHEMA_OK", flush=True)
        break
    except (ProgrammingError, OperationalError, InternalError) as e:
        print("ERR", str(e)[:400], flush=True)
        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        if not plan:
            raise
        mig = plan[0][0]
        print(f"FAKE {mig.app_label} {mig.name}", flush=True)
        call_command("migrate", mig.app_label, mig.name, fake=True, interactive=False, verbosity=1)
        connection.close()
else:
    raise SystemExit("too many migrate rounds")
call_command("collectstatic", interactive=False, verbosity=0, clear=True)
print("BOOTSTRAP_OK", flush=True)
PY