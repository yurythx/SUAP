#!/bin/bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
export PATH="$HOME/.local/bin:$PATH"
apt-get update -qq || true
apt-get install -y -qq build-essential libpq-dev libjpeg-dev zlib1g-dev libffi-dev \
  git pkg-config libxml2-dev libxslt1-dev libssl-dev curl ca-certificates \
  python3 python3-venv python3-pip
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"
mkdir -p /opt/suap /var/log/suap /opt/suap/deploy/media /opt/suap/static /opt/suap/deploy/logs
uv --version
echo APP_BASE_OK
