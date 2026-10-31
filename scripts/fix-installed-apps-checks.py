#!/usr/bin/env python3
"""Replace brittle "'app' in settings.INSTALLED_APPS" with apps.is_installed('app')."""
import re
from pathlib import Path

root = Path("/opt/suap/src")
# Match: 'foo' in settings.INSTALLED_APPS  (and double quotes)
pat = re.compile(r"(['\"])([a-zA-Z0-9_]+)\1\s+in\s+settings\.INSTALLED_APPS")
fixed = 0
for path in root.rglob("migrations/*.py"):
    text = path.read_text(encoding="utf-8")
    new, n = pat.subn(r"apps.is_installed(\1\2\1)", text)
    if n:
        path.write_text(new, encoding="utf-8")
        fixed += n
        print(f"{path}: {n}")
print(f"TOTAL_FIXED={fixed}")
