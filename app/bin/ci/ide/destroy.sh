#!/usr/bin/env bash
set -axe
CONTAINER_NAME="code-server-$USERNAME"
VOLUME_PATH="/var/suapdevs/$CONTAINER_NAME"
docker stop "$CONTAINER_NAME" || true
rm -rf "$VOLUME_PATH"
