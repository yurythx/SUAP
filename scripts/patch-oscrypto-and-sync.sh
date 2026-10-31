#!/bin/bash
set -euo pipefail
cd /opt/suap/src
python3 -c "
from pathlib import Path
p = Path('pyproject.toml')
t = p.read_text()
old = 'oscrypto = { git = \"https://github.com/wbond/oscrypto.git\", rev = \"1547f53\" }'
new = 'oscrypto = { path = \"/opt/suap/vendor/oscrypto\" }'
if old in t:
    p.write_text(t.replace(old, new))
    print('pyproject patched')
elif new in t:
    print('already patched')
else:
    raise SystemExit('oscrypto line not found')
"
export http_proxy=http://192.168.29.78:8899
export https_proxy=http://192.168.29.78:8899
export HTTP_PROXY="$http_proxy"
export HTTPS_PROXY="$https_proxy"
export ALL_PROXY="$http_proxy"
export UV_HTTP_TIMEOUT=600
export UV_CONCURRENT_DOWNLOADS=2
uv lock --python 3.14
uv sync --python 3.14 --all-groups
echo UV_SYNC_OK
