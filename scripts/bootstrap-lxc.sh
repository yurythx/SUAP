#!/bin/bash
# Bootstrap mínimo por papel — rodar no LXC (root). Usa proxy apt se configurado.
set -euo pipefail
ROLE="${1:?role: db|redis|app|lb|ctl}"
export DEBIAN_FRONTEND=noninteractive

apt-get update -qq
apt-get install -y -qq ca-certificates curl wget gnupg2 python3 python3-venv python3-pip rsync

case "$ROLE" in
  db)
    apt-get install -y -qq postgresql postgresql-contrib
    # listen on internal + mgmt
    PG_CONF=$(ls /etc/postgresql/*/main/postgresql.conf | head -1)
    PG_HBA=$(ls /etc/postgresql/*/main/pg_hba.conf | head -1)
    sed -i "s/#listen_addresses = 'localhost'/listen_addresses = '*'/" "$PG_CONF" || \
      sed -i "s/listen_addresses = 'localhost'/listen_addresses = '*'/" "$PG_CONF"
    grep -q '192.168.110.0/24' "$PG_HBA" || echo 'host all all 192.168.110.0/24 scram-sha-256' >> "$PG_HBA"
    systemctl enable --now postgresql
    : "${DATABASE_PASSWORD:?Defina DATABASE_PASSWORD}"
    db_pass=${DATABASE_PASSWORD//\'/\'\'}
    runuser -u postgres -- psql -tc "SELECT 1 FROM pg_roles WHERE rolname='suap'" | grep -q 1 || \
      runuser -u postgres -- psql -c "CREATE USER suap WITH PASSWORD '${db_pass}';"
    runuser -u postgres -- psql -tc "SELECT 1 FROM pg_database WHERE datname='suap'" | grep -q 1 || \
      runuser -u postgres -- psql -c "CREATE DATABASE suap OWNER suap;"
    runuser -u postgres -- psql -c "ALTER USER suap WITH PASSWORD '${db_pass}';"
    systemctl restart postgresql
    echo "DB_OK"
    ;;
  redis)
    apt-get install -y -qq redis-server
    sed -i 's/^bind .*/bind 0.0.0.0/' /etc/redis/redis.conf
    sed -i 's/^protected-mode yes/protected-mode no/' /etc/redis/redis.conf
    : "${REDIS_PASSWORD:?Defina REDIS_PASSWORD}"
    grep -q '^requirepass' /etc/redis/redis.conf || echo "requirepass ${REDIS_PASSWORD}" >> /etc/redis/redis.conf
    sed -i "s/^# requirepass .*/requirepass ${REDIS_PASSWORD}/" /etc/redis/redis.conf
    sed -i "s/^requirepass .*/requirepass ${REDIS_PASSWORD}/" /etc/redis/redis.conf
    systemctl enable --now redis-server
    systemctl restart redis-server
    echo "REDIS_OK"
    ;;
  lb)
    apt-get install -y -qq nginx
    cat >/etc/nginx/sites-available/suap <<'NGX'
map $http_x_forwarded_proto $suap_forwarded_proto {
    default $http_x_forwarded_proto;
    ""      $scheme;
}
server {
    listen 80 default_server;
    server_name hmlsuap.rondonopolis.mt.gov.br 192.168.29.110 192.168.110.10 _;
    client_max_body_size 100m;
    set_real_ip_from 192.168.0.218;
    real_ip_header X-Forwarded-For;
    real_ip_recursive on;
    location / {
        proxy_pass http://192.168.110.20:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $suap_forwarded_proto;
        proxy_set_header X-Forwarded-Host $host;
        proxy_read_timeout 300;
    }
    location /static/ {
        alias /var/www/suap-static/;
        expires 7d;
    }
}
NGX
    ln -sfn /etc/nginx/sites-available/suap /etc/nginx/sites-enabled/suap
    rm -f /etc/nginx/sites-enabled/default
    mkdir -p /var/www/suap-static
    nginx -t && systemctl enable --now nginx && systemctl reload nginx
    echo "LB_OK"
    ;;
  app)
    apt-get install -y -qq build-essential libpq-dev libjpeg-dev zlib1g-dev libffi-dev \
      git pkg-config libxml2-dev libxslt1-dev libssl-dev
    # uv
    if ! command -v uv >/dev/null 2>&1; then
      curl -LsSf https://astral.sh/uv/install.sh | sh
      export PATH="$HOME/.local/bin:$PATH"
      echo 'export PATH="$HOME/.local/bin:$PATH"' >> /root/.bashrc
    fi
    mkdir -p /opt/suap /var/log/suap /opt/suap/deploy/media /opt/suap/static
    echo "APP_BASE_OK"
    ;;
  ctl)
    apt-get install -y -qq ansible sshpass git
    echo "CTL_OK"
    ;;
  *)
    echo "unknown role"; exit 1
    ;;
esac
