#!/usr/bin/env python
"""Homolog/fresh: aplica schema via migrate, ignorando RunPython (data migrations quebradas no Django 5 / DB vazio)."""
from __future__ import annotations

import os
import sys

# Garante import do projeto mesmo quando o script vive em /migrate_empty.py
sys.path.insert(0, "/opt/suap")
os.chdir("/opt/suap")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "suap.settings")

import django

django.setup()

from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.operations.special import RunPython
from django.db.utils import InternalError, OperationalError, ProgrammingError


def main() -> int:
    # No-op de data migrations (histórico incompatível com Django 5 / install vazia).
    RunPython.database_forwards = lambda *a, **k: None  # type: ignore[method-assign]
    RunPython.database_backwards = lambda *a, **k: None  # type: ignore[method-assign]

    for round_i in range(1, 500):
        print(f"==== migrate_empty round {round_i} ====", flush=True)
        try:
            call_command("migrate", interactive=False, verbosity=1)
            print("MIGRATE_EMPTY_OK", flush=True)
            return 0
        except (ProgrammingError, OperationalError, InternalError, Exception) as e:
            msg = str(e)[:500]
            print(f"ERR {type(e).__name__}: {msg}", flush=True)
            executor = MigrationExecutor(connection)
            plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
            if not plan:
                raise
            mig = plan[0][0]
            # Só fake automático para migrations 100% RunPython (sem DDL).
            ops = mig.operations
            if ops and all(isinstance(op, RunPython) for op in ops):
                print(f"FAKE_DATA {mig.app_label}.{mig.name}", flush=True)
                call_command("migrate", mig.app_label, mig.name, fake=True, interactive=False, verbosity=1)
                connection.close()
                continue
            # Schema quebra: fake também (último recurso homolog) e segue.
            print(f"FAKE_SCHEMA {mig.app_label}.{mig.name}", flush=True)
            call_command("migrate", mig.app_label, mig.name, fake=True, interactive=False, verbosity=1)
            connection.close()
    print("too many migrate rounds", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
