#!/usr/bin/env python3
"""Adapta o payload Codex ao núcleo compartilhado de C901 do SUAP."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from common import raiz_git


def main() -> int:
    """Executa o núcleo e propaga apenas a reprovação C901 (status 2)."""
    payload = sys.stdin.read()
    raiz = raiz_git(Path.cwd())
    ambiente = {**os.environ, 'CLAUDE_PROJECT_DIR': str(raiz)}
    ambiente.setdefault('UV_CACHE_DIR', str(Path(tempfile.gettempdir(), 'suap-codex-uv-cache')))
    resultado = subprocess.run(
        [str(raiz / '.agents/hooks/check_complexity.py')],
        input=payload,
        cwd=raiz,
        env=ambiente,
        capture_output=True,
        text=True,
        check=False,
    )
    if resultado.stderr:
        print(resultado.stderr.rstrip(), file=sys.stderr)
    return 2 if resultado.returncode == 2 else 0


if __name__ == '__main__':
    raise SystemExit(main())
