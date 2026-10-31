#!/usr/bin/env python3
"""Fix buggy apps.get_model('app.Model') one-arg calls in migrations."""
import re
from pathlib import Path

root = Path("/opt/suap/src")
pat = re.compile(
    r"apps\.get_model\(\s*['\"]([a-zA-Z0-9_]+)\.([A-Za-z0-9_]+)['\"]\s*\)"
)
fixed = 0
for path in root.rglob("migrations/*.py"):
    text = path.read_text(encoding="utf-8")
    new, n = pat.subn(r"apps.get_model('\1', '\2')", text)
    if n:
        path.write_text(new, encoding="utf-8")
        fixed += n
        print(f"{path}: {n}")
print(f"TOTAL_FIXED={fixed}")
