#!/usr/bin/env bash
set -axe
. .env

USER_ID=${1:-GITLAB_USER_ID}
PASSWORD=${2:-$(openssl rand -hex 3)}
CONTAINER_NAME="code-server-$USERNAME"
VOLUME_PATH="/var/suapdevs/$CONTAINER_NAME"
CONTAINER=$(docker ps --format "{{.Names}}" -a --no-trunc --filter name=^/"$CONTAINER_NAME")
SITE_URL="http://$USER_ID.$DOMAIN_NAME"

if ! [ -d "$VOLUME_PATH" ]; then cp -r "$(pwd)" "$VOLUME_PATH"; fi

if ! [ "$CONTAINER" ]; then
  docker run --rm --name "$CONTAINER_NAME" --network=ci_suap-network -p 8000:8000 -p 8080:8080 -d -e PASSWORD="$PASSWORD" -l PASSWORD="$PASSWORD" -v "$(pwd)":/suap suap-ide
  docker exec -w /suap "$CONTAINER_NAME" cp suap/settings_sample.py suap/settings.py
  docker exec -w /suap "$CONTAINER_NAME" git pull origin master
fi

PASSWORD=$(docker ps -f name="$CONTAINER_NAME" --format "{{.Label \"PASSWORD\"}}")
echo "URL: $SITE_URL SENHA: $PASSWORD"