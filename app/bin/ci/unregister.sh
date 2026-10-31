#!/usr/bin/env bash
set -axe

FULLPATH="$( cd "$(dirname "$0")" ; cd ../.. ; pwd -P )"
cd $FULLPATH

. .env

gitlab-runner unregister --all-runners
gitlab-runner stop
