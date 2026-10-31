#!/bin/bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
PG_CONF=$(ls /etc/postgresql/*/main/postgresql.conf | head -1)
PG_HBA=$(ls /etc/postgresql/*/main/pg_hba.conf | head -1)
sed -i "s/^#\?listen_addresses.*/listen_addresses = '*'/" "$PG_CONF"
grep -q '192.168.110.0/24' "$PG_HBA" || echo 'host all all 192.168.110.0/24 scram-sha-256' >> "$PG_HBA"
: "${DATABASE_PASSWORD:?Defina DATABASE_PASSWORD}"
db_pass=${DATABASE_PASSWORD//\'/\'\'}
systemctl enable --now postgresql
runuser -u postgres -- psql -tc "SELECT 1 FROM pg_roles WHERE rolname='suap'" | grep -q 1 || \
  runuser -u postgres -- psql -c "CREATE USER suap WITH PASSWORD '${db_pass}';"
runuser -u postgres -- psql -tc "SELECT 1 FROM pg_database WHERE datname='suap'" | grep -q 1 || \
  runuser -u postgres -- psql -c "CREATE DATABASE suap OWNER suap;"
runuser -u postgres -- psql -c "ALTER USER suap WITH PASSWORD '${db_pass}';"
systemctl restart postgresql
ss -lntp | grep 5432 || true
echo DB_OK
