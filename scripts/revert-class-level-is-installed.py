#!/usr/bin/env python3
"""Revert apps.is_installed back to settings.INSTALLED_APPS outside functions."""
import re
from pathlib import Path

root = Path("/opt/suap/src")
# crude: at class Migration level (indent 4 spaces, line starts with if/ternary using apps.is_installed)
# Safer: restore ALL apps.is_installed('x') that appear at module/class scope by checking indent
# and restoring settings check for dependency-style uses.

# Restore pattern only when NOT inside a def (approx: lines with indent <= 8 that aren't inside RunPython)
# Simplest reliable approach: restore all apps.is_installed to settings check,
# then re-apply apps.is_installed ONLY inside lines that also call get_model nearby... messy.

# Do targeted restore of known broken files + any Migration class dependency lines.
pat = re.compile(r"apps\.is_installed\((['\"])([a-zA-Z0-9_]+)\1\)")

def should_keep_is_installed(line: str, in_def: bool) -> bool:
    if in_def:
        return True
    return False

for path in root.rglob("migrations/*.py"):
    lines = path.read_text(encoding="utf-8").splitlines(True)
    out = []
    in_def = 0
    changed = 0
    for line in lines:
        # track def depth roughly by indent of 'def '
        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)
        if re.match(r"def\s+\w+\(", stripped):
            in_def = indent
        elif in_def and indent <= in_def and stripped and not stripped.startswith("#"):
            # left the function
            if not stripped.startswith("@"):
                in_def = 0

        if "apps.is_installed(" in line and not in_def:
            new_line, n = pat.subn(r"\1\2\1 in settings.INSTALLED_APPS", line)
            if n:
                line = new_line
                changed += n
        out.append(line)
    if changed:
        path.write_text("".join(out), encoding="utf-8")
        print(f"{path}: restored {changed}")
print("DONE")
