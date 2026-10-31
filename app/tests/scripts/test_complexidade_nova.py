"""Regressões do hook `bin/scripts/complexidade-nova.py` num repositório git temporário.

Rodar: `uv run python tests/scripts/test_complexidade_nova.py` (ou via pytest).
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / 'bin' / 'scripts' / 'complexidade-nova.py'


def _funcao(nome: str, ramos: int, indent: str = '') -> str:
    corpo = ''.join(f'{indent}    if x == {i}:\n{indent}        return {i}\n' for i in range(ramos))
    return f'{indent}def {nome}(x):\n{corpo}{indent}    return -1\n'


LEGADO = 'class A:\n' + _funcao('clean', 12, '    ') + '\n\nclass B:\n' + _funcao('clean', 3, '    ')


def _sh(repo: Path, *cmd: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=repo, capture_output=True, text=True, check=False, env={**os.environ, **(env or {})})


def _repo(tmp: Path) -> Path:
    _sh(tmp, 'git', 'init', '-q', '-b', 'master')
    _sh(tmp, 'git', 'config', 'user.email', 't@t')
    _sh(tmp, 'git', 'config', 'user.name', 't')
    (tmp / 'mod.py').write_text(LEGADO)
    _sh(tmp, 'git', 'add', '.')
    _sh(tmp, 'git', 'commit', '-qm', 'base')
    return tmp


def _hook(repo: Path, *arquivos: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return _sh(repo, sys.executable, str(SCRIPT), *arquivos, env=env)


def test_legado_editado_passa_e_novo_reprova() -> None:
    with tempfile.TemporaryDirectory() as d:
        repo = _repo(Path(d))
        # editar o legado complexo (A.clean) não é cobrado
        (repo / 'mod.py').write_text(LEGADO.replace('return -1', 'return -2', 1))
        assert _hook(repo, 'mod.py').returncode == 0
        # legado complexo que melhora passa; que piora reprova
        (repo / 'mod.py').write_text(LEGADO.replace(_funcao('clean', 12, '    '), _funcao('clean', 11, '    ')))
        assert _hook(repo, 'mod.py').returncode == 0
        (repo / 'mod.py').write_text(LEGADO.replace(_funcao('clean', 12, '    '), _funcao('clean', 13, '    ')))
        proc = _hook(repo, 'mod.py')
        assert proc.returncode == 1, proc.stderr
        assert '[era 13]' in proc.stderr, proc.stderr
        # B.clean cruzou o limite: mesmo nome de A.clean, outra classe
        (repo / 'mod.py').write_text('class A:\n' + _funcao('clean', 12, '    ') + '\n\nclass B:\n' + _funcao('clean', 11, '    '))
        proc = _hook(repo, 'mod.py')
        assert proc.returncode == 1, proc.stderr
        assert proc.stderr.count('  - mod.py:') == 1, proc.stderr
        # arquivo novo com função complexa
        (repo / 'mod.py').write_text(LEGADO)
        (repo / 'novo.py').write_text(_funcao('f', 11))
        _sh(repo, 'git', 'add', 'novo.py')
        assert _hook(repo, 'mod.py', 'novo.py').returncode == 1


def test_git_mv_e_modo_ci() -> None:
    with tempfile.TemporaryDirectory() as d:
        repo = _repo(Path(d))
        _sh(repo, 'git', 'checkout', '-qb', 'mr')
        (repo / 'pacote').mkdir()
        _sh(repo, 'git', 'mv', 'mod.py', 'pacote/mod.py')
        assert _hook(repo, 'pacote/mod.py').returncode == 0
        _sh(repo, 'git', 'commit', '-qm', 'mv')
        (repo / 'novo.py').write_text(_funcao('f', 11))
        _sh(repo, 'git', 'add', 'novo.py')
        _sh(repo, 'git', 'commit', '-qm', 'novo')
        ci = {'PRE_COMMIT_FROM_REF': 'master', 'PRE_COMMIT_TO_REF': 'HEAD'}
        assert _hook(repo, 'pacote/mod.py', env=ci).returncode == 0
        assert _hook(repo, 'pacote/mod.py', 'novo.py', env=ci).returncode == 1


if __name__ == '__main__':
    test_legado_editado_passa_e_novo_reprova()
    test_git_mv_e_modo_ci()
    sys.stdout.write('ok\n')
