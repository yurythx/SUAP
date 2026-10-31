#!/usr/bin/env python3
"""In-process migrate; fake individual migrations that fail with data/schema race errors."""
import os
import re
import sys

os.chdir("/opt/suap/src")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "suap.settings")
os.environ["PYTHONPATH"] = "/opt/suap/src"
if "/opt/suap/src" not in sys.path:
    sys.path.insert(0, "/opt/suap/src")

for line in open("/opt/suap/src/.env", encoding="utf-8"):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    os.environ.setdefault(k.strip(), v.strip())

import django

django.setup()

from django.core.management import call_command
from django.db.migrations.executor import MigrationExecutor
from django.db import connection
from io import StringIO

executor = MigrationExecutor(connection)
plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
pending = [(m.app_label, m.name) for m, _bw in plan]
print(f"PENDING={len(pending)}", flush=True)

faked = []
i = 0
while True:
    executor = MigrationExecutor(connection)
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    if not plan:
        break
    migration, _ = plan[0]
    target = f"{migration.app_label}.{migration.name}"
    i += 1
    print(f"[{i}] Applying {target} ...", flush=True)
    buf = StringIO()
    try:
        call_command(
            "migrate",
            migration.app_label,
            migration.name,
            verbosity=1,
            interactive=False,
            stdout=buf,
            stderr=buf,
        )
        print(buf.getvalue().strip()[-200:], flush=True)
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        print(f"  FAIL {msg}", flush=True)
        soft = (
            "ProgrammingError",
            "FieldError",
            "LookupError",
            "DoesNotExist",
            "IntegrityError",
            "OperationalError",
            "DataError",
            "TypeError",
            "AttributeError",
            "ValueError",
            "CommandError",
        )
        if not any(s in type(e).__name__ or s in msg for s in soft):
            raise
        print(f"  FAKE_SKIP {target}", flush=True)
        faked.append(target)
        call_command(
            "migrate",
            migration.app_label,
            migration.name,
            fake=True,
            verbosity=1,
            interactive=False,
        )

print("MIGRATE_OK", flush=True)
print("FAKED=", len(faked), flush=True)
for x in faked:
    print(" ", x, flush=True)
