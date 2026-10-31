from pathlib import Path

p = Path("/opt/suap/src/comum/migrations/0079_auto_20240902_0911.py")
t = p.read_text(encoding="utf-8")
# Force-safe version: never require estagios app at migrate time
import re

t2 = re.sub(
    r"Aprendizagem = \(.*?else None\n    \)",
    "Aprendizagem = None  # homolog: estagios may be listed but not loaded",
    t,
    count=1,
    flags=re.S,
)
if t2 == t:
    # try original one-liner variants
    t2 = re.sub(
        r"Aprendizagem = apps\.get_model\([^\n]+",
        "Aprendizagem = None  # homolog patch",
        t,
        count=1,
    )
if "Aprendizagem = None" not in t2:
    raise SystemExit("failed to patch\n" + t)
p.write_text(t2, encoding="utf-8")
print("patched 0079 to skip estagios")
