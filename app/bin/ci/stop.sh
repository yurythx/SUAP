#!/usr/bin/env bash
set -axe

FULLPATH="$( cd "$(dirname "$0")" ; cd ../.. ; pwd -P )"
cd $FULLPATH

. .env

docker-compose -f bin/ci/docker-compose.yaml down
