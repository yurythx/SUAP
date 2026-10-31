#!/bin/bash
set -o errexit
set -o nounset

PARENTSCRIPTPATH="$( cd "$(dirname "$0")" ; cd .. ; pwd -P )"
CELERY_BROKER_URL=${1:-"redis://localhost:6379/3"}
FLOWER_BASIC_AUTH=${2:-"usu4r10:s3nh4"}
cd $PARENTSCRIPTPATH ; celery -b "${CELERY_BROKER_URL}" flower --purge_offline_workers=1 --basic_auth=$FLOWER_BASIC_AUTH
