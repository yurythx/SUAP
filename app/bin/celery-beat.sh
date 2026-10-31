#!/usr/bin/env bash

PARENTSCRIPTPATH="$( cd "$(dirname "$0")" ; cd .. ; pwd -P )"
cd $PARENTSCRIPTPATH ; celery -A suap beat -l debug --scheduler beat.schedulers:DatabaseSchedulerPlus
