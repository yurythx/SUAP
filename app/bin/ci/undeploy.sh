#!/usr/bin/env bash
set -axe

. "$(dirname "$0")/suapdev-comum.sh" "$@"

BRANCH_NAME=${branch:-none}
OWNER=${owner:-none}

if [ "$BRANCH_NAME" = "none" ] || [ "$OWNER" = "none" ]; then
  echo "Comando inválido, formato correto do comando: ./undeploy.sh --branch nomebranch --owner dono"
  exit 1
fi

SLUG=$(slug "$BRANCH_NAME")
CONTAINER_NAME="deploy-$SLUG"
sudo rm -rf "/home/gitlab-runner/$SLUG" "/var/suapdevs/$SLUG"

registrar_acao undeploy
docker stop "$CONTAINER_NAME"
docker rm "$CONTAINER_NAME"
