#!/bin/bash
set -euo pipefail
mkdir -p /opt/suap/vendor
cd /opt/suap/src
rm -rf .venv
tar -xzf /opt/suap/suap-venv.tgz
PYHOME=/root/.local/share/uv/python/cpython-3.14.10-linux-x86_64-gnu
cat > .venv/pyvenv.cfg <<EOF
home = $PYHOME/bin
include-system-site-packages = false
version = 3.14.10
executable = $PYHOME/bin/python3.14
command = uv sync
EOF
ln -sfn "$PYHOME/bin/python3.14" .venv/bin/python
ln -sfn "$PYHOME/bin/python3.14" .venv/bin/python3
ln -sfn "$PYHOME/bin/python3.14" .venv/bin/python3.14
.venv/bin/python -c "import django; print('DJANGO', django.get_version())"
.venv/bin/python -c "import gunicorn; print('GUNICORN_OK')"
echo VENV_OK
