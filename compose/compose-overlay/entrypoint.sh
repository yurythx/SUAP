#!/usr/bin/env bash
set -euo pipefail

ROLE="${1:-gunicorn}"

wait_for_tcp() {
  local host="$1" port="$2" retries="${3:-90}"
  echo "[entrypoint] aguardando ${host}:${port}"
  for _ in $(seq 1 "${retries}"); do
    if (echo >"/dev/tcp/${host}/${port}") >/dev/null 2>&1; then
      echo "[entrypoint] ${host}:${port} ok"
      return 0
    fi
    sleep 2
  done
  echo "[entrypoint] timeout ${host}:${port}" >&2
  return 1
}

cd /opt/suap
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-suap.settings}"
export PATH="/venv/bin:${PATH}"

DB_HOST="${DATABASE_HOST:-db}"
DB_PORT="${DATABASE_PORT:-5432}"
REDIS_HOST="${REDIS_HOST:-redis}"
REDIS_PORT="${REDIS_PORT:-6379}"

wait_for_tcp "${DB_HOST}" "${DB_PORT}"
if [[ "${USE_REDIS:-True}" == "True" ]]; then
  wait_for_tcp "${REDIS_HOST}" "${REDIS_PORT}"
fi

mkdir -p deploy/logs/supervisor deploy/media/tmp static || true

case "${ROLE}" in
  gunicorn)
    if [[ "${SKIP_DB_INIT:-False}" == "True" ]]; then
      echo "[entrypoint] SKIP_DB_INIT=True"
    elif [[ "${HOMOLOG_SKIP_DATA_MIGRATIONS:-False}" == "True" ]]; then
      echo "[entrypoint] homolog: migrate sem RunPython + sync parcial"
      python /migrate_empty.py
      python manage.py gerar_metadados || true
      python manage.py loaddata initial_data --skip-checks --ignore || true
      python manage.py sync_permissions || true
      python manage.py collectstatic --noinput -v 0 || true
      python manage.py carregar_apis -v 0 || true
      python manage.py importar_tarefas_celery_beat -v 0 || true
    elif [[ "${RUN_SYNC_ON_START:-True}" == "True" ]]; then
      echo "[entrypoint] executando manage.py sync (bootstrap oficial)"
      python manage.py sync || python manage.py migrate --noinput
    else
      python manage.py migrate --noinput
    fi

    exec gunicorn suap.wsgi:application \
      --bind 0.0.0.0:8000 \
      --workers "${GUNICORN_WORKERS:-6}" \
      --threads "${GUNICORN_THREADS:-2}" \
      --timeout "${GUNICORN_TIMEOUT:-120}" \
      --max-requests 1000 \
      --max-requests-jitter 50 \
      --graceful-timeout 30 \
      --keep-alive 5 \
      --access-logfile - \
      --error-logfile - \
      --capture-output
    ;;
  celery-worker)
    exec celery -A suap worker -l INFO -Q "${CELERY_QUEUE:-geral}" --concurrency="${CELERY_CONCURRENCY:-4}"
    ;;
  celery-beat)
    exec celery -A suap beat -l INFO --scheduler django_celery_beat.schedulers:DatabaseScheduler
    ;;
  *)
    exec "$@"
    ;;
esac