#!/bin/bash
set -euo pipefail
cd /opt/suap/src
set -a
# shellcheck disable=SC1091
source /opt/suap/src/.env
set +a
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-suap.settings}"
export PYTHONPATH=/opt/suap/src

# DB connectivity
.venv/bin/python - <<'PY'
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', os.environ.get('DJANGO_SETTINGS_MODULE','suap.settings'))
django.setup()
from django.db import connection
connection.ensure_connection()
print('DB_CONN_OK')
PY

.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py collectstatic --noinput || true

# systemd units
cat >/etc/systemd/system/suap-gunicorn.service <<'UNIT'
[Unit]
Description=SUAP Gunicorn
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/suap/src
EnvironmentFile=/opt/suap/src/.env
Environment=DJANGO_SETTINGS_MODULE=suap.settings
Environment=PYTHONPATH=/opt/suap/src
ExecStart=/opt/suap/src/.venv/bin/gunicorn suap.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers ${GUNICORN_WORKERS:-2} \
  --threads ${GUNICORN_THREADS:-2} \
  --timeout ${GUNICORN_TIMEOUT:-120} \
  --access-logfile - \
  --error-logfile -
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

cat >/etc/systemd/system/suap-celery.service <<'UNIT'
[Unit]
Description=SUAP Celery Worker
After=network.target redis.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/suap/src
EnvironmentFile=/opt/suap/src/.env
Environment=DJANGO_SETTINGS_MODULE=suap.settings
Environment=PYTHONPATH=/opt/suap/src
ExecStart=/opt/suap/src/.venv/bin/celery -A suap worker -Q ${CELERY_QUEUE:-geral} -c ${CELERY_CONCURRENCY:-2} -l INFO
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now suap-gunicorn.service
systemctl enable --now suap-celery.service || true
sleep 2
systemctl --no-pager --full status suap-gunicorn.service | head -25
curl -sS -o /dev/null -w 'HTTP %{http_code}\n' http://127.0.0.1:8000/ || true
echo APP_START_OK
