#!/usr/bin/env python3
"""Adapta o gate de commit compartilhado (``.agents/hooks/commit_gate.py``) ao Codex."""

from __future__ import annotations

import json
import sys

from common import carregar_modulo, raiz_git


def main() -> int:
    """Autoriza o Bash com entrada reescrita quando o gate se aplica (o Codex exige ``allow``)."""
    raiz = raiz_git('.')
    gate = carregar_modulo(raiz / '.agents/hooks/commit_gate.py', 'commit_gate_codex')
    entrada = gate.entrada_com_gate(gate.hook_payload.carregar_payload(sys.stdin.read()))
    if entrada is None:
        return 0
    print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'allow', 'updatedInput': entrada}}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
