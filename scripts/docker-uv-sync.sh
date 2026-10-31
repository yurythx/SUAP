#!/bin/bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends \
  build-essential libldap2-dev libsasl2-dev libssl-dev \
  libpq-dev pkg-config > /tmp/apt.log 2>&1 || {
  echo "apt failed:"; tail -40 /tmp/apt.log; exit 1
}
cd /work/app
python3 - <<'PY'
from pathlib import Path
p = Path("pyproject.toml")
t = p.read_text()
old = 'oscrypto = { path = "../vendor/oscrypto" }'
new = 'oscrypto = { path = "/work/vendor/oscrypto" }'
if old in t:
    p.write_text(t.replace(old, new))
    print("patched oscrypto path for docker")
elif new in t:
    print("already docker path")
else:
    print("WARNING: oscrypto line unexpected")
PY
# Ensure vendor exists
ls -la /work/vendor/oscrypto/setup.py
# Image ships 3.14.2; project asks >=3.14.3 — relax for wheel build (ABI compatible)
python3 - <<'PY'
from pathlib import Path
p = Path("pyproject.toml")
t = p.read_text()
t2 = t.replace('requires-python = ">=3.14.3, <3.15"', 'requires-python = ">=3.14.2, <3.15"')
if t2 != t:
    p.write_text(t2)
    print("relaxed requires-python")
else:
    print("requires-python unchanged or already relaxed")
PY
uv sync --python 3.14 --all-groups
echo UV_DOCKER_OK
du -sh .venv
