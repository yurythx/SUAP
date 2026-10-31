#!/usr/bin/env python3
"""Gate de commit compartilhado: põe as checagens do CI na frente de ``git commit``.

Vale para qualquer segmento do comando (``git add -A && git commit -m x`` também passa
pelo gate); ``--no-verify``/``-n`` no segmento do commit pulam, como no git. Se uma
checagem falhar, o ``&&`` para e o commit não acontece.

CLI (Claude Code; o adaptador do Codex e o plugin do OpenCode reusam a mesma regra):
lê o payload do hook no stdin e, quando o gate se aplica, imprime ``updatedInput`` sem
``permissionDecision``: o comando reescrito segue o fluxo normal de permissão, nada é
auto-aprovado. Roda no ``python3`` do sistema (3.12) a cada Bash: nada de sintaxe 3.14.
"""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hook_payload

# `uv run` usa o ruff/pre-commit pinados no .venv do projeto; o shell do agente nem sempre tem o venv no PATH.
CHECKS = (
    'uv run --quiet ruff format .',
    'uv run --quiet ruff check . --fix --unsafe-fixes',
    'git add -u',
    'uv run --quiet pre-commit run --from-ref origin/master --to-ref HEAD',
)
_OPERADORES = {'&&', '||', ';', '|', '&', '(', ')', '\n'}


def _segmentos(comando: str) -> list[list[str]]:
    """Quebra o comando nos operadores de shell, respeitando aspas."""
    lexer = shlex.shlex(comando, posix=True, punctuation_chars=';&|()\n')
    lexer.whitespace = ' \t\r'
    lexer.whitespace_split = True
    segmentos: list[list[str]] = [[]]
    for token in lexer:
        if token in _OPERADORES or set(token) <= set(';&|()\n'):
            segmentos.append([])
        else:
            segmentos[-1].append(token)
    return [s for s in segmentos if s]


def _sem_atribuicoes(tokens: list[str]) -> list[str]:
    """Descarta ``VAR=valor`` do início do segmento."""
    while tokens and '=' in tokens[0] and not tokens[0].startswith('-'):
        tokens = tokens[1:]
    return tokens


def deve_aplicar_gate(comando: str) -> bool:
    """Há um segmento ``git commit`` e nenhum deles pediu ``--no-verify``/``-n``."""
    try:
        commits = [s for s in map(_sem_atribuicoes, _segmentos(comando)) if s[:2] == ['git', 'commit']]
    except ValueError:
        return False
    return bool(commits) and not any('--no-verify' in s or '-n' in s for s in commits)


def comando_com_gate(comando: str) -> str:
    """Prefixa os checks sem reescrever argumentos ou quoting do comando original."""
    return ' && '.join((*CHECKS, comando))


def entrada_com_gate(payload: dict) -> dict | None:
    """``tool_input`` reescrito, ou ``None`` quando o gate não se aplica."""
    entrada = payload.get('tool_input') or {}
    comando = entrada.get('command') if isinstance(entrada, dict) else None
    if not isinstance(comando, str) or not deve_aplicar_gate(comando):
        return None
    return {**entrada, 'command': comando_com_gate(comando)}


def main() -> int:
    """Imprime o ``updatedInput`` do PreToolUse quando o gate se aplica."""
    entrada = entrada_com_gate(hook_payload.carregar_payload(sys.stdin.read()))
    if entrada is not None:
        print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'updatedInput': entrada}}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
