#!/usr/bin/env python3
"""Bloqueia (exit 2) edições destinadas a arquivos ``.env*``, em qualquer harness.

Lê o payload do hook no stdin: ``tool_input.file_path`` (Claude Code), patch V4A ou
unified diff em ``tool_input.command`` (Codex). Roda no ``python3`` do sistema (3.12):
não use sintaxe exclusiva do 3.14 aqui nem em ``hook_payload.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hook_payload


def arquivo_env(caminho: str) -> bool:
    """Informa se o basename segue a política ``.env``/``.env.*``."""
    nome = Path(caminho).name
    return nome == '.env' or nome.startswith('.env.')


def main() -> int:
    """Nega antes da escrita quando qualquer destino do payload for ``.env*``."""
    payload = hook_payload.carregar_payload(sys.stdin.read())
    proibidos = [path for path in hook_payload.caminhos_do_payload(payload) if arquivo_env(path)]
    if not proibidos:
        return 0
    print(
        f'BLOQUEADO: edite arquivos .env manualmente para evitar vazamento de credenciais: {", ".join(proibidos)}',
        file=sys.stderr,
    )
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
