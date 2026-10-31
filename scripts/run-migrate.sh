#!/bin/bash
set -euo pipefail
cd /opt/suap/src
set -a
# shellcheck disable=SC1091
source /opt/suap/src/.env
set +a
export DJANGO_SETTINGS_MODULE=suap.settings
export PYTHONPATH=/opt/suap/src
.venv/bin/python manage.py migrate --noinput
echo MIGRATE_OK
