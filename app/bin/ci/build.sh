#!/usr/bin/env bash
set -axe

FULLPATH="$( cd "$(dirname "$0")" ; cd ../.. ; pwd -P )"
cd $FULLPATH

IMAGE="suap-${1:-base}"

# 1. Carregamento de Ambiente
if [ -f .env ]; then
  while IFS='=' read -r key value; do
    if [[ ! $key =~ ^# && -n $key ]]; then
      value=$(echo "$value" | sed -e 's/^"//' -e 's/"$//')
      export "$key=$value"
    fi
  done < .env
fi

if [ -z "$2" ]; then
  make build-base
  docker build -f bin/ci/Dockerfile --build-arg base_image="$SUAP_IMAGE:base" -t "$IMAGE" --target "$IMAGE" .
else
  mkdir -p /tmp/build
  cp $FULLPATH/pyproject.toml /tmp/build/pyproject.toml
  cp $FULLPATH/uv.lock /tmp/build/uv.lock
  if [ "$2" = "packages" ]; then
    printf "FROM %s\nADD pyproject.toml pyproject.toml\nADD uv.lock uv.lock\nRUN %s" "$IMAGE" "uv sync --all-groups" > /tmp/build/Dockerfile
  else
    printf "FROM %s\nRUN %s" "$IMAGE" "$2" > /tmp/build/Dockerfile
  fi
  docker build -f /tmp/build/Dockerfile -t "$IMAGE" /tmp/build/
fi
