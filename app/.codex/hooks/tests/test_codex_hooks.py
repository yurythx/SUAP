"""Testes dos contratos de hooks versionados para o Codex."""

from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / '.codex/hooks'))


def _modulo(nome: str) -> ModuleType:
    caminho = RAIZ / '.codex/hooks' / f'{nome}.py'
    spec = importlib.util.spec_from_file_location(f'codex_{nome}', caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_saida_do_gate_segue_schema_codex() -> None:
    hook = _modulo('pre_commit')
    payload = {'tool_input': {'command': 'git commit -m x', 'justification': 'teste'}}
    with patch('sys.stdin', io.StringIO(json.dumps(payload))), redirect_stdout(io.StringIO()) as saida:
        assert hook.main() == 0
    retorno = json.loads(saida.getvalue())['hookSpecificOutput']
    assert retorno['hookEventName'] == 'PreToolUse'
    assert retorno['permissionDecision'] == 'allow'
    assert retorno['updatedInput']['justification'] == 'teste'


def test_registro_de_mr_nunca_propaga_falha() -> None:
    hook = _modulo('register_mr_time_spent')
    payload = {'tool_name': 'Bash', 'tool_input': {'command': 'glab mr update 42'}}
    with (
        patch.object(hook.sys, 'stdin', io.StringIO(json.dumps(payload))),
        patch.object(hook.subprocess, 'run', side_effect=subprocess.SubprocessError('falha')),
    ):
        assert hook.main() == 0


def test_registro_de_mr_filtra_bash_e_aceita_mcp() -> None:
    hook = _modulo('register_mr_time_spent')
    assert not hook.evento_relevante({'tool_name': 'Bash', 'tool_input': {'command': 'git push'}})
    assert not hook.evento_relevante({'tool_name': 'Bash', 'tool_input': {'command': 'echo glab mr create'}})
    assert hook.evento_relevante({'tool_name': 'Bash', 'tool_input': {'command': 'glab mr create --draft'}})
    assert hook.evento_relevante({'tool_name': 'mcp__gitlab__create_merge_request', 'tool_input': {}})


def test_manifesto_nao_contem_segredos_ou_caminhos_pessoais() -> None:
    manifesto = (RAIZ / '.codex/hooks.json').read_text()
    json.loads(manifesto)
    assert 'token' not in manifesto.lower()
    assert '/Users/' not in manifesto
    assert '~/.codex' not in manifesto
