#!/usr/bin/env bash
set -axe
CONTAINER_NAME="code-server-$USERNAME"
docker stop "$CONTAINER_NAME"
