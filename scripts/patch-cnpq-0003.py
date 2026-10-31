from pathlib import Path

p = Path("/opt/suap/src/cnpq/migrations/0003_auto_20210518_1127.py")
t = p.read_text(encoding="utf-8")
# Make RunPython a no-op — command needs columns added in later migrations
if "call_command('atualizar_datas_do_servidor')" in t:
    t = t.replace(
        "call_command('atualizar_datas_do_servidor')",
        "pass  # skipped: depends on columns from later migrations",
    )
    p.write_text(t, encoding="utf-8")
    print("patched cnpq.0003")
else:
    print("already patched or pattern missing")
    print(t[:500])
