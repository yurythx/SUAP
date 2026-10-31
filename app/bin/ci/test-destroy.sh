#!/usr/bin/env bash
set -axe
BRANCH="${1:-master}"
JOB_NAME=${2:test}
JOB_ID=${3:default}
BRANCH_SAFE=$(echo "$BRANCH" | tr '/:@' '-' | tr -cd '[:alnum:]_.' | md5sum | awk '{print $1}' | cut -c 1-10)
CONTAINER="$JOB_NAME-$BRANCH_SAFE-$JOB_ID"
docker stop "$CONTAINER" 2> /dev/null || true
docker exec postgres dropdb --if-exists -U postgres "$CONTAINER"
