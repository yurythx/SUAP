#!/bin/bash
set -euo pipefail
cd /opt/suap/compose

echo "=== stop app containers ==="
sudo docker compose -p suap -f docker-compose.prod.yml stop web celery_worker celery_beat nginx || true
sudo docker compose -p suap -f docker-compose.prod.yml stop db || true

echo "=== current tree ==="
sudo find /opt/suap/data/postgres -maxdepth 3 -printf '%u:%g %m %p\n' | head -40

echo "=== chown 999:999 recursively ==="
sudo chown -R 999:999 /opt/suap/data/postgres
sudo chmod 700 /opt/suap/data/postgres

echo "=== start db ==="
sudo docker compose -p suap -f docker-compose.prod.yml up -d db
sleep 10
sudo docker compose -p suap -f docker-compose.prod.yml ps db
sudo docker logs suap-db --tail 25

# Se ainda estiver quebrado, reinicializa (homolog)
if sudo docker logs suap-db 2>&1 | tail -5 | grep -q "Permission denied"; then
  echo "=== REINIT DB (homolog) ==="
  sudo docker compose -p suap -f docker-compose.prod.yml stop db
  sudo rm -rf /opt/suap/data/postgres/*
  sudo chown -R 999:999 /opt/suap/data/postgres
  sudo docker compose -p suap -f docker-compose.prod.yml up -d db
  sleep 15
  sudo docker logs suap-db --tail 30
fi

sudo docker exec suap-db pg_isready -U suap -d suap
echo "=== start stack ==="
sudo docker compose -p suap -f docker-compose.prod.yml up -d
echo DONE
