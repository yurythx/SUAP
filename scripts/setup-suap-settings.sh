#!/bin/bash
set -euo pipefail
cd /opt/suap/src
cp -n suap/settings_sample.py suap/settings.py || true
python3 <<'PY'
from pathlib import Path
p = Path("suap/settings.py")
text = p.read_text(encoding="utf-8")
marker = "os.environ.get('DATABASE_HOST'"
if marker not in text:
    p.write_text(
        text
        + """

# --- overlays LXC homolog ---
import os
DATABASES['default'].update({
    'NAME': os.environ.get('DATABASE_NAME', DATABASES['default'].get('NAME', 'suap')),
    'USER': os.environ.get('DATABASE_USER', DATABASES['default'].get('USER', 'suap')),
    'PASSWORD': os.environ.get('DATABASE_PASSWORD', DATABASES['default'].get('PASSWORD', '')),
    'HOST': os.environ.get('DATABASE_HOST', DATABASES['default'].get('HOST', '127.0.0.1')),
    'PORT': os.environ.get('DATABASE_PORT', DATABASES['default'].get('PORT', '5432')),
})
SECRET_KEY = os.environ.get('SECRET_KEY', SECRET_KEY)
ALLOWED_HOSTS = [h for h in os.environ.get('ALLOWED_HOSTS', 'localhost').split(',') if h]
DEBUG = os.environ.get('DEBUG', 'False') == 'True'
"""
        ,
        encoding="utf-8",
    )
    print("settings patched")
else:
    print("settings already env-aware")
PY
echo SETTINGS_OK
