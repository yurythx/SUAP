#!/usr/bin/env bash
FULLPATH="$( cd "$(dirname "$0")" ; cd ../.. ; pwd -P )"
cd "$FULLPATH"
. .env

echo "" > bin/ci/nginx/suapdevs.conf

while IFS= read -r name ; do
 if [ -n "$name" ]; then
  printf "server {
 server_name %s.$DOMAIN_NAME;
 location / {
  proxy_set_header Host $DOMAIN_NAME;
  proxy_pass http://deploy-%s;
 }
}
" "$name" "$name" >> bin/ci/nginx/suapdevs.conf
 fi
done <<< "$(docker ps --format '{{.Label "BRANCH"}}' | grep -v -e '^$')"

docker restart web
