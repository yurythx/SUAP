#!/usr/bin/env bash
set -axe

. "$(dirname "$0")/suapdev-comum.sh" "$@"

BRANCH_NAME=${branch:-master}
SLUG=$(slug "$BRANCH_NAME")
DATABASE_TEMPLATE_NAME=${database:-${DATABASE_TEMPLATE}}
PASSWORD=${password:-$(openssl rand -hex 3)}
USERNAMES=${usernames}
OWNER=${owner:-none}
MAX_MEMORY_SIZE=${maxmemory:-1024m}
MAX_MEMORY_SWAP=${maxmemoryswap:-2048m}
DATABASE_NAME="database-$SLUG-suap"
VOLUME_PATH="/var/suapdevs/$SLUG"
CONTAINER_NAME="deploy-$SLUG"
CONTAINER=$(docker ps --format "{{.Names}}" -a --no-trunc --filter name=^/"$CONTAINER_NAME$")
DATABASE=$(docker exec postgres psql -h "$DATABASE_HOST" -U postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$DATABASE_NAME'")
SITE_URL="http://$SLUG.$DOMAIN_NAME"

dexec() { docker exec -e HOME=/tmp -w /suap "$CONTAINER_NAME" "$@"; }

registrar_acao deploy

if ! [ -d "$VOLUME_PATH" ]; then
  sudo cp -r "$FULLPATH" "$VOLUME_PATH"
fi

sudo git -C "$VOLUME_PATH" checkout .
sudo git -C "$VOLUME_PATH" pull origin -X ours --no-edit "$BRANCH_NAME"

if ! [ "$DATABASE" ]; then
  docker exec postgres psql -U postgres -h "$DATABASE_HOST" -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DATABASE_TEMPLATE_NAME'"
  docker exec postgres createdb -h "$DATABASE_HOST" -U postgres -T "$DATABASE_TEMPLATE_NAME" "$DATABASE_NAME"
fi

if ! [ "$CONTAINER" ]; then
  docker run --name "$CONTAINER_NAME" --env-file .env --network=ci_suap-network --restart unless-stopped -it -d \
    -v "$VOLUME_PATH":/suap -w /suap -e DATABASE_NAME="$DATABASE_NAME" -e SITE_URL="$SITE_URL" -p 80 \
    -l suapdev -l OWNER="$OWNER" -l BRANCH="$SLUG" -l PASSWORD="$PASSWORD" -l DATE="$(date +%d/%m/%Y)" suap-dev
  dexec cp suap/settings_sample.py suap/settings.py
fi

dexec uv sync --all-groups

# O sync precisa de memória folgada; o trap devolve o limite mesmo se ele falhar (antes o container ficava com 32g).
docker update --memory 32g --memory-swap 32g "$CONTAINER_NAME"
trap 'docker update --memory "$MAX_MEMORY_SIZE" --memory-swap "$MAX_MEMORY_SWAP" "$CONTAINER_NAME"' EXIT
dexec python manage.py sync

dexec python manage.py set_passwords_to "$PASSWORD" "$USERNAMES"
dexec supervisorctl restart suap
echo "URL: $SITE_URL SENHA: $PASSWORD"
