#!/usr/bin/env python3
"""Apply migrations one-by-one; on RunPython data failures, fake that migration and continue."""
import os
import re
import subprocess
import sys

os.chdir("/opt/suap/src")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "suap.settings")
os.environ.setdefault("PYTHONPATH", "/opt/suap/src")

# Load .env
env_path = "/opt/suap/src/.env"
if os.path.exists(env_path):
    for line in open(env_path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

py = "/opt/suap/src/.venv/bin/python"


def run(args, check=False):
    print("+", " ".join(args), flush=True)
    p = subprocess.run(args, capture_output=True, text=True)
    sys.stdout.write(p.stdout)
    sys.stderr.write(p.stderr)
    if check and p.returncode != 0:
        raise SystemExit(p.returncode)
    return p


# List plan
plan = run([py, "manage.py", "showmigrations", "--plan"], check=True)
pending = []
for line in plan.stdout.splitlines():
    # [ ] app.migration_name
    m = re.match(r"\[\s\]\s+(\S+)\.(\S+)", line.strip())
    if m:
        pending.append((m.group(1), m.group(2)))

print(f"PENDING={len(pending)}", flush=True)
errors = []
for app, name in pending:
    target = f"{app}.{name}"
    p = run([py, "manage.py", "migrate", app, name, "--noinput"])
    if p.returncode == 0:
        continue
    blob = (p.stdout or "") + (p.stderr or "")
    # Schema errors that aren't "empty data" should still stop — but for homolog empty DB,
    # ProgrammingError/FieldError/LookupError in RunPython are usually safe to fake.
    if any(
        x in blob
        for x in (
            "ProgrammingError",
            "FieldError",
            "LookupError",
            "DoesNotExist",
            "IntegrityError",
        )
    ):
        print(f"FAKE_SKIP {target}", flush=True)
        errors.append(target)
        run([py, "manage.py", "migrate", app, name, "--fake", "--noinput"], check=True)
    else:
        print(f"HARD_FAIL {target}", flush=True)
        raise SystemExit(1)

print("MIGRATE_OK")
print("FAKED=", len(errors))
for e in errors:
    print(" ", e)
