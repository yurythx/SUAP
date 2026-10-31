#!/usr/bin/env bash
set -axe

FULLPATH="$( cd "$(dirname "$0")" ; cd ../.. ; pwd -P )"
cd $FULLPATH

. .env

docker run --rm --name suap_dev --network=ci_suap-network -it -d -v "$(pwd)":/suap -e BEHAVE_CHROME_HEADLESS=True -e BEHAVE_AUTO_MOCK=True -e DATABASE_NAME="$DATABASE_TEMPLATE" -w /suap suap-base
if ! [ -f "suap.sql" ]; then
  docker exec suap_dev /etc/init.d/postgresql start && sleep 15
  docker exec suap_dev git pull origin master
  docker exec suap_dev python manage.py collectstatic --noinput
  docker exec suap_dev python manage.py test_behave --settings suap.settings_sample --behave_stop comum
else
  docker exec suap_dev dropdb -U postgres -h "$DATABASE_HOST" --if-exists "$DATABASE_TEMPLATE"
  docker exec suap_dev createdb -U postgres -h "$DATABASE_HOST" "$DATABASE_TEMPLATE"
  docker exec suap_dev psql -U postgres -h "$DATABASE_HOST" -d "$DATABASE_TEMPLATE" -f suap.sql
  docker exec -e DATABASE_HOST="$DATABASE_HOST" suap_dev python manage.py migrate --settings suap.settings_sample --fake
fi

docker stop suap_dev
