"""Testes das guardas compartilhadas: ``protect_env`` e ``commit_gate``.

Rode com ``pytest .agents/hooks/test_guardas.py`` (o pytest não desce em diretório oculto sozinho).
"""

from __future__ import annotations

import importlib.util
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from types import ModuleType
from unittest.mock import patch


def _nucleo(nome: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f'nucleo_{nome}', Path(__file__).with_name(f'{nome}.py'))
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_bloqueia_env_em_patch_multiarquivo() -> None:
    hook = _nucleo('protect_env')
    payload = {'tool_input': {'command': '*** Begin Patch\n*** Update File: comum/a.py\n*** Add File: .env.local\n*** End Patch'}}
    with patch('sys.stdin', io.StringIO(json.dumps(payload))):
        assert hook.main() == 2


def test_bloqueia_variantes_env() -> None:
    hook = _nucleo('protect_env')
    assert all(hook.arquivo_env(nome) for nome in ('.env', '.env.dev', 'config/.env.local'))
    assert not hook.arquivo_env('exemplo.env')


def test_env_apenas_no_conteudo_nao_bloqueia() -> None:
    hook = _nucleo('protect_env')
    payload = {'tool_input': {'command': '*** Update File: comum/a.py\n+texto = ".env.local"'}}
    with patch('sys.stdin', io.StringIO(json.dumps(payload))):
        assert hook.main() == 0


def test_bloqueia_remocao_env_em_unified_diff() -> None:
    hook = _nucleo('protect_env')
    payload = {'tool_input': {'command': '--- a/.env.dev\n+++ /dev/null\n@@ -1 +0,0 @@\n-SEGREDO=x'}}
    with patch('sys.stdin', io.StringIO(json.dumps(payload))):
        assert hook.main() == 2


def test_bloqueia_rename_env_em_unified_diff() -> None:
    hook = _nucleo('protect_env')
    payload = {'tool_input': {'command': '--- a/.env.local\n+++ b/configuracao.txt'}}
    with patch('sys.stdin', io.StringIO(json.dumps(payload))):
        assert hook.main() == 2


def test_unified_diff_sem_env_continua_permitido() -> None:
    hook = _nucleo('protect_env')
    payload = {'tool_input': {'command': '--- a/comum/a.py\n+++ b/comum/a.py\n@@ -1 +1 @@\n-antigo\n+texto = ".env.dev"'}}
    with patch('sys.stdin', io.StringIO(json.dumps(payload))):
        assert hook.main() == 0


def test_gate_preserva_commit_e_quoting() -> None:
    hook = _nucleo('commit_gate')
    comando = 'git commit -m "mensagem com espaços"'
    assert hook.deve_aplicar_gate(comando)
    assert hook.comando_com_gate(comando).endswith(comando)
    assert hook.comando_com_gate(comando).split(' && ')[:4] == list(hook.CHECKS)


def test_gate_respeita_escape_e_evitar_falso_positivo() -> None:
    hook = _nucleo('commit_gate')
    assert not hook.deve_aplicar_gate('git commit --no-verify -m x')
    assert not hook.deve_aplicar_gate('git commit -n -m x')
    assert not hook.deve_aplicar_gate('echo "rode git commit"')
    assert not hook.deve_aplicar_gate('git commit-msg arquivo')


def test_gate_vale_em_qualquer_segmento() -> None:
    hook = _nucleo('commit_gate')
    assert hook.deve_aplicar_gate('git status && git commit -m x')
    assert hook.deve_aplicar_gate('cd /tmp && REGISTRAR=1 git commit -am "a && b"')
    assert not hook.deve_aplicar_gate('git add -A && git commit -n -m x')
    assert not hook.deve_aplicar_gate('git log | grep commit')
    assert not hook.deve_aplicar_gate('git commit -m "aspas abertas')


def test_cli_do_gate_nao_auto_aprova() -> None:
    hook = _nucleo('commit_gate')
    payload = {'tool_name': 'Bash', 'tool_input': {'command': 'git commit -m x', 'description': 'd'}}
    with patch('sys.stdin', io.StringIO(json.dumps(payload))), redirect_stdout(io.StringIO()) as saida:
        assert hook.main() == 0
    retorno = json.loads(saida.getvalue())['hookSpecificOutput']
    assert 'permissionDecision' not in retorno
    assert retorno['updatedInput'] == {'command': hook.comando_com_gate('git commit -m x'), 'description': 'd'}


def test_protect_env_le_file_path_do_claude() -> None:
    hook = _nucleo('protect_env')
    for caminho, esperado in (('/repo/.env', 2), ('/repo/comum/a.py', 0)):
        with patch('sys.stdin', io.StringIO(json.dumps({'tool_input': {'file_path': caminho}}))):
            assert hook.main() == esperado
