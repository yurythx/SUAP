#!/usr/bin/env bash
set -axe

. "$(dirname "$0")/suapdev-comum.sh" "$@"

BRANCH_NAME=${branch:-none}
OWNER=${owner:-none}

if [ "$BRANCH_NAME" = "none" ] || [ "$OWNER" = "none" ]; then
  echo "Comando inválido, formato correto do comando: ./destroy.sh --branch nomebranch --owner dono"
  exit 1
fi

SLUG=$(slug "$BRANCH_NAME")
CONTAINER_NAME="deploy-$SLUG"
DATABASE_NAME="database-$SLUG-suap"
sudo rm -rf "/home/gitlab-runner/$SLUG" "/var/suapdevs/$SLUG"
# O container pode já ter sido removido (undeploy anterior); sob `set -e` isso abortava o script antes do DROP.
docker stop "$CONTAINER_NAME" || true
docker rm "$CONTAINER_NAME" || true
# FORCE encerra as conexões (inclusive as do pool do pgbouncer); IF EXISTS torna o destroy repetível.
docker exec postgres psql -U postgres -h "$DATABASE_HOST" -c "DROP DATABASE IF EXISTS \"$DATABASE_NAME\" WITH (FORCE);"
# Registrado só depois do DROP: antes o log dizia "destroy" mesmo quando o banco ficava.
registrar_acao destroy
