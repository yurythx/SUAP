#!/usr/bin/env bash

CELERY_QUEUE=${1:-geral}

while [ $# -gt 0 ]; do
   if [[ $1 == "--autoreload" ]]; then declare AUTORELOAD=1; else declare AUTORELOAD=0; fi
  shift
done

PARENTSCRIPTPATH="$( cd "$(dirname "$0")" ; cd .. ; pwd -P )"

if [[ $AUTORELOAD -eq 0 ]]; then
  echo "Starting celery"
  cd $PARENTSCRIPTPATH ; celery -A suap worker -l INFO -Q $CELERY_QUEUE
else
  echo "Starting celery with autoreload"
  cd $PARENTSCRIPTPATH ; watchmedo auto-restart --directory=./ --pattern=*.py --recursive -- celery -A suap worker -l INFO -Q $CELERY_QUEUE  --loglevel=INFO
fi
