#!/usr/bin/env bash
set -axe

FULLPATH="$( cd "$(dirname "$0")" ; cd ../.. ; pwd -P )"
cd $FULLPATH

. .env

CI_PROJECT_DIR="/var/suapdevs/build-doc"
CONTAINER="build-doc"
BEHAVE_CONFIGURATION=$(printf "BEHAVE_AUTO_DOC = True\nBEHAVE_AUTO_MOCK = True\nBEHAVE_AUTO_DOC_PATH = \'/tmp/documentacao\'\nBEHAVE_AUTO_MOCK_PATH = \'/tmp/documentacao/sql\'")
DOCKER_EXEC="docker exec -w /suap $CONTAINER"

git pull origin master
rm -rf $CI_PROJECT_DIR /tmp/documentacao
cp -r $FULLPATH $CI_PROJECT_DIR

cp /tmp/documentacao/sql/suap_mock.sql /root/ || true

mkdir -p /tmp/documentacao/sql
docker rm -f "$CONTAINER" || true
docker run --rm --name "$CONTAINER" -it -d -v $CI_PROJECT_DIR:/suap -e CI_PROJECT_DIR=$CI_PROJECT_DIR -v /tmp:/tmp -e SUAP_CHECK="generate_doc" -e BEHAVE_CHROME_HEADLESS=1 -w /suap suap-base

$DOCKER_EXEC /etc/init.d/postgresql start || true
$DOCKER_EXEC createdb -U postgres suap_dev || true
$DOCKER_EXEC cp suap/settings_sample.py suap/settings.py || true
$DOCKER_EXEC bash -c "echo \"$BEHAVE_CONFIGURATION\" | tee -a suap/settings.py" || true
$DOCKER_EXEC uv sync --all-groups || true
$DOCKER_EXEC python manage.py collectstatic --skip-checks -v 0 --noinput || true
$DOCKER_EXEC python manage.py suap_check
$DOCKER_EXEC dropdb -h "$DATABASE_HOST" --if-exists -U postgres behave || true
$DOCKER_EXEC createdb -h "$DATABASE_HOST" -U postgres behave || true
$DOCKER_EXEC sh -c "psql -h $DATABASE_HOST -U postgres behave < /tmp/documentacao/sql/suap_mock.sql" || true
$DOCKER_EXEC zip -r -j /tmp/documentacao/documentacao.zip /tmp/documentacao || true
docker stop "$CONTAINER" || true
./bin/ci/build.sh test packages
