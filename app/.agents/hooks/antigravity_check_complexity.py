#!/usr/bin/env python3
"""Adapta o hook Stop do Antigravity ao núcleo compartilhado de C901 do SUAP.

O PostToolUse do Antigravity só aceita `{}` como resposta (não bloqueia nem devolve
nada ao modelo); o Stop aceita `{"decision": "continue", "reason": ...}`, que injeta
`reason` como mensagem de sistema e devolve o agente ao loop. Por isso a checagem
roda quando o agente vai encerrar, no modo sem argumentos do núcleo (.py modificados
vs HEAD + não rastreados). Só o exit 2 do núcleo segura o agente; árvore limpa,
ruff ausente ou qualquer falha deixam encerrar. O Antigravity limita as continuações
seguidas, o que evita laço quando o agente não consegue refatorar.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

NUCLEO = Path(__file__).resolve().with_name('check_complexity.py')


def raiz_do_workspace(payload: dict) -> Path:
    """Raiz git do primeiro workspace do payload; sem ele, o repositório deste script."""
    caminhos = payload.get('workspacePaths')
    base = Path(caminhos[0]) if isinstance(caminhos, list) and caminhos and isinstance(caminhos[0], str) else NUCLEO.parents[2]
    proc = subprocess.run(['git', 'rev-parse', '--show-toplevel'], cwd=base, capture_output=True, text=True, check=False)
    return Path(proc.stdout.strip()) if proc.returncode == 0 else base


def checar(raiz: Path) -> subprocess.CompletedProcess[str]:
    """Roda o núcleo sem stdin (o JSON do Stop não é payload de ferramenta)."""
    ambiente = {**os.environ, 'CLAUDE_PROJECT_DIR': str(raiz)}
    ambiente.setdefault('UV_CACHE_DIR', str(Path(tempfile.gettempdir(), 'suap-antigravity-uv-cache')))
    # O Antigravity só repassa variáveis de ambiente de uma lista fixa: o `uv` do shebang pode
    # não estar no PATH do hook, então prefere o python 3.14 do .venv do repositório.
    python_venv = NUCLEO.parents[2] / '.venv/bin/python'
    comando = [str(python_venv), str(NUCLEO)] if python_venv.is_file() else [str(NUCLEO)]
    return subprocess.run(comando, input='', cwd=raiz, env=ambiente, capture_output=True, text=True, check=False)


def main() -> int:
    """Sempre sai 0 com JSON válido; `continue` só quando há função tocada acima de 10."""
    # ponytail: checa todo .py sujo vs HEAD, inclusive mudança do usuário que o agente não fez;
    # se incomodar, gravar os TargetFile num PostToolUse e passá-los como argumentos aqui.
    resposta = {'decision': ''}
    try:
        payload = json.loads(sys.stdin.read() or '{}')
        resultado = checar(raiz_do_workspace(payload if isinstance(payload, dict) else {}))
        if resultado.returncode == 2:
            resposta = {'decision': 'continue', 'reason': f'{resultado.stderr.strip()}\nRefatore antes de encerrar a tarefa.'}
    except (OSError, ValueError, subprocess.SubprocessError) as erro:
        print(f'check_complexity (Antigravity): {erro}', file=sys.stderr)
    print(json.dumps(resposta, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
