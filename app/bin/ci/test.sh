#!/usr/bin/env bash
set -axe
BRANCH=${1:-master}
TARGET_BRANCH=${2:-master}
CI_PROJECT_DIR=${3}
JOB_ID=${4}
JOB_NAME=${5:test}
SUAP_CHECK=${6}
SUAP_APPS=${7}
BRANCH_SAFE=$(echo "$BRANCH" | tr '/:@' '-' | tr -cd '[:alnum:]_.' | md5sum | awk '{print $1}' | cut -c 1-10)
CONTAINER="$JOB_NAME-$BRANCH_SAFE-$JOB_ID"
EXEC="docker exec -w /suap $CONTAINER"
docker rm -f "$CONTAINER" || true
git pull origin master --no-rebase
HOST_UID=$(id -u)
HOST_GID=$(id -g)
docker run -it --rm --name "$CONTAINER" -d \
    --init \
    --user "$HOST_UID:$HOST_GID" \
    --shm-size=2g \
    --memory=8g \
    --memory-reservation=1g \
    --ulimit nofile=65535:65535 \
    --network ci_suap-network \
    -v $CI_PROJECT_DIR:/suap \
    -v /root/.ssh:/tmp/.ssh:ro \
    -v /root/.gitconfig:/tmp/.gitconfig:ro \
    -e HOME=/tmp \
    -e XDG_CACHE_HOME=/tmp/.cache \
    -e UV_CACHE_DIR=/tmp/.cache/uv \
    -e DATABASE_HOST="postgres" \
    -e SUAP_CHECK="$SUAP_CHECK" \
    -e SUAP_APPS="$SUAP_APPS" \
    -e TEST_DATABASE_NAME="$CONTAINER" \
    suap-test

set +e
$EXEC cp suap/settings_sample.py suap/settings.py
$EXEC uv sync --all-groups
$EXEC python manage.py collectstatic --skip-checks -v 0 --noinput
$EXEC python manage.py suap_check
SUAP_EXIT_CODE=$?
set -e

if [ "$SUAP_EXIT_CODE" -ne 0 ]; then
    echo "=========================================================="
    echo ">>> suap_check falhou (exit $SUAP_EXIT_CODE)"
    # 137 = 128 + SIGKILL(9): processo morto de fora, normalmente OOM do cgroup.
    OOM_KILLED=$(docker inspect -f '{{.State.OOMKilled}}' "$CONTAINER" 2>/dev/null || echo unknown)
    echo ">>> Container OOMKilled: $OOM_KILLED"
    if [ "$SUAP_EXIT_CODE" -eq 137 ] || [ "$OOM_KILLED" = "true" ]; then
        echo ">>> SIGKILL detectado: os testes NAO falharam; o processo foi morto (provavel OOM)."
        echo ">>> O pytest foi interrompido antes de imprimir os tracebacks."
        echo ">>> Acoes: reduzir paralelismo (pytest -n 1) ou aumentar --memory do container (atual: 8g)."
    fi
    echo "=========================================================="
fi

exit $SUAP_EXIT_CODE
