#!/usr/bin/env python3
"""Encaminha eventos Codex de MR ao registrador compartilhado, sem bloquear."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

from common import carregar_modulo, raiz_git


def evento_relevante(payload: dict) -> bool:
    """Filtra Bash cedo e aceita ferramentas de criação/atualização de MR."""
    ferramenta = str(payload.get('tool_name') or '')
    if re.search(r'(create|update)_merge_request', ferramenta):
        return True
    entrada = payload.get('tool_input') or {}
    comando = entrada.get('command') if isinstance(entrada, dict) else None
    if ferramenta != 'Bash' or not isinstance(comando, str):
        return False
    try:
        partes = shlex.split(comando)
    except ValueError:
        return False
    return len(partes) >= 3 and partes[:2] == ['glab', 'mr'] and partes[2] in ('create', 'update')


def main() -> int:
    """Preserva payload, cwd e transcript_path; qualquer falha continua best-effort."""
    payload_bruto = sys.stdin.read()
    try:
        raiz = raiz_git(Path.cwd())
        normalizador = carregar_modulo(raiz / '.agents/hooks/hook_payload.py', 'hook_payload_codex_mr')
        if not evento_relevante(normalizador.carregar_payload(payload_bruto)):
            return 0
        ambiente = {**os.environ, 'CLAUDE_PROJECT_DIR': str(raiz)}
        resultado = subprocess.run(
            [str(raiz / '.agents/hooks/register_mr_time_spent.py')],
            input=payload_bruto,
            cwd=raiz,
            env=ambiente,
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as erro:
        print(f'[codex/register_mr_time_spent] falha no adaptador: {erro}', file=sys.stderr)
        return 0
    if resultado.stderr:
        print(resultado.stderr.rstrip(), file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
