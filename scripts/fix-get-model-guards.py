#!/usr/bin/env python3
"""On lines that call get_model and check INSTALLED_APPS, use apps.is_installed instead."""
import re
from pathlib import Path

root = Path("/opt/suap/src")
pat = re.compile(r"(['\"])([a-zA-Z0-9_]+)\1\s+in\s+settings\.INSTALLED_APPS")
fixed = 0
for path in root.rglob("migrations/*.py"):
    lines = path.read_text(encoding="utf-8").splitlines(True)
    out = []
    file_fixed = 0
    for line in lines:
        if "get_model" in line and "settings.INSTALLED_APPS" in line:
            new_line, n = pat.subn(r"apps.is_installed(\1\2\1)", line)
            if n:
                line = new_line
                file_fixed += n
        out.append(line)
    if file_fixed:
        path.write_text("".join(out), encoding="utf-8")
        fixed += file_fixed
        print(f"{path}: {file_fixed}")
print(f"TOTAL_FIXED={fixed}")
