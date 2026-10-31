#!/usr/bin/env bash
set -axe

FULLPATH="$( cd "$(dirname "$0")" ; cd ../.. ; pwd -P )"
cd $FULLPATH

docker compose -f bin/ci/docker-compose.yaml up --detach
sleep 10
docker exec -it postgres createdb -U postgres suap_dev || true
