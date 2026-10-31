#!/usr/bin/env bash
set -axe

FULLPATH="$( cd "$(dirname "$0")" ; cd ../.. ; pwd -P )"
cd $FULLPATH

. .env
gitlab-runner register --non-interactive --url "$GITLAB_URL" --registration-token "$RUNNER_TOKEN" --executor "shell" --description "$(hostname)" --tag-list "$RUNNER_TAGS" --run-untagged="true" --locked="false"
gitlab-runner start
