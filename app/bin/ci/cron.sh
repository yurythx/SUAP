#!/usr/bin/env bash

while [ $# -gt 0 ]; do
   if [[ $1 == *"--"* ]]; then param="${1/--/}"; declare "$param"="$2"; fi
  shift
done

BRANCH_NAME=${branch:-master}
DATABASE_TEMPLATE_NAME=${database:-suap_pequeno_mascarado}
PASSWORD=${password:-$(openssl rand -hex 3)}
DESTROY=${destroy:-false}

FULLPATH="$( cd "$(dirname "$0")" ; cd ../.. ; pwd -P )"
cd $FULLPATH

git pull origin master

docker ps -a --filter status=running | grep "deploy-" | grep "Up 4 weeks" | awk '{{ print $14 }}' | xargs docker stop || true
sleep 20

if [ $DESTROY = 'true' ]; then
  echo "Destroy $BRANCH_NAME"
  ./bin/ci/destroy.sh --branch $BRANCH_NAME --owner "admin" || true
else
  echo "Undeploy $BRANCH_NAME"
  ./bin/ci/undeploy.sh --branch $BRANCH_NAME --owner "admin" || true
fi

sleep 20

echo "Deploy $BRANCH_NAME"
./bin/ci/deploy.sh --branch $BRANCH_NAME --owner "admin" --database $DATABASE_TEMPLATE_NAME --password $PASSWORD || true

sleep 20

echo "Indexando $BRANCH_NAME"
./bin/ci/index.sh

date
printf "\n\n\n"
