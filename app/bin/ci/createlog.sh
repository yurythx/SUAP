#!/usr/bin/env bash
set -axe

FULLPATH="$( cd "$(dirname "$0")" ; cd ../.. ; pwd -P )"
cd $FULLPATH

. .env

CREATE_TABLE=$(cat <<-EOM
create table suapdevs
(
  id serial,
  nome text,
  dono text default 'admin' not null,
  acao text,
  data timestamp default now() not null
);

create unique index suapdevs_id_uindex
  on suapdevs (id);

alter table suapdevs
  add constraint suapdevs_pk
    primary key (id);
EOM
)

echo $CREATE_TABLE

echo "Criando banco suapdevs"
docker run --rm --name suapdevs --network=ci_suap-network -it -d suap-base
docker exec suapdevs psql -h "$DATABASE_HOST" -U postgres -tAc "create database suapdevs" || true
echo "Criando tabela suapdevs"
docker exec suapdevs psql -h "$DATABASE_HOST" -U postgres -d suapdevs -tAc "$CREATE_TABLE"

docker stop suapdevs
