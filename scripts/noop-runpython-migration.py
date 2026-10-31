#!/usr/bin/env python3
"""Turn RunPython ops into noop for a given migration file path (argv1)."""
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
# Replace migrations.RunPython(...) with noop form when it's a single function reference
# Safer: replace function bodies that are the first arg of RunPython by making them pass
# For this specific failure, rewrite file to only noop operations if RunPython present.
if "RunPython.noop" in text and "RunPython(" not in text.replace("RunPython.noop", ""):
    print("already noop-ish")
    sys.exit(0)

# Append a forced noop migration operations override via rewriting operations list
# Simplest robust approach: make every def used by RunPython just `pass`
import re

# Find functions that are first args to RunPython and blank them
funcs = re.findall(r"migrations\.RunPython\(\s*([a-zA-Z_][a-zA-Z0-9_]*)", text)
for fn in funcs:
    text2, n = re.subn(
        rf"(def {fn}\([^)]*\):\n)(?:(?:[ \t].*\n)+)",
        rf"\1    return  # noop for empty homolog DB\n",
        text,
        count=1,
    )
    if n:
        text = text2
        print(f"noop {fn}")
path.write_text(text, encoding="utf-8")
print("patched", path)
