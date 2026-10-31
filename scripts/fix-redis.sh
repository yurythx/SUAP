#!/bin/bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq || true
apt-get install -y -qq redis-server
sed -i 's/^bind .*/bind 0.0.0.0/' /etc/redis/redis.conf
sed -i 's/^protected-mode yes/protected-mode no/' /etc/redis/redis.conf
: "${REDIS_PASSWORD:?Defina REDIS_PASSWORD}"
if grep -q '^requirepass\|^# requirepass' /etc/redis/redis.conf; then
  sed -i "s/^#\? requirepass .*/requirepass ${REDIS_PASSWORD}/" /etc/redis/redis.conf
else
  echo "requirepass ${REDIS_PASSWORD}" >> /etc/redis/redis.conf
fi
systemctl enable --now redis-server
systemctl restart redis-server
redis-cli -a "$REDIS_PASSWORD" ping
echo REDIS_OK
