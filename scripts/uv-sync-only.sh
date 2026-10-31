#!/bin/bash
set -euo pipefail
export http_proxy=http://192.168.29.78:8899
export https_proxy=http://192.168.29.78:8899
export HTTP_PROXY="$http_proxy"
export HTTPS_PROXY="$https_proxy"
export ALL_PROXY="$http_proxy"
export UV_HTTP_TIMEOUT=300
export UV_CONCURRENT_DOWNLOADS=4
ip route replace 192.168.0.0/16 via 192.168.29.253 dev eth1 2>/dev/null || true
cd /opt/suap/src
uv sync --python 3.14 --all-groups
echo UV_SYNC_OK
