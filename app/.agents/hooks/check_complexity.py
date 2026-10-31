#!/usr/bin/env -S uv run --quiet python3
"""Bloqueia funcoes TOCADAS com complexidade ciclomatica > 10 (ruff C901).

Pode ser acionado de duas formas:
1. Hook de agentes (Claude Code/Codex: PostToolUse; OpenCode: tool.execute.after):
   Le o JSON do hook no stdin e descobre os arquivos .py editados. Edicao de arquivo
   que nao e .py nao tem o que checar (exit 0).
2. Standalone / CLI (desenvolvedor ou agentes no terminal; Antigravity: hook Stop):
   - Com argumentos: `check_complexity.py path/to/file.py ...` checa so os arquivos
     passados. Caminho relativo vale a partir do cwd (e, se nao existir, da raiz).
   - Sem argumentos: checa os .py modificados (vs HEAD) e os nao rastreados.

Nos dois modos so reprova funcao cujo corpo intersecta linhas diferentes do HEAD
(git diff): funcoes legadas intocadas no mesmo arquivo sao ignoradas, e um arquivo
rastreado sem diff nao tem funcao tocada. Arquivo novo (nao rastreado) conta inteiro.
Para checar um arquivo inteiro, use o ruff direto
(`ruff check --select C901 --config lint.mccabe.max-complexity=10 <arquivo>`).

Exit: 0 = nada acima de 10; 2 = funcao tocada acima de 10 (mensagem no stderr);
1 = nao deu para checar (ruff/git ausente ou com erro, argumento que nao e um .py
existente, nenhum arquivo para checar no modo sem argumentos).
Nao afeta o ruff dos desenvolvedores; no pre-commit vale a regra mais branda de
`bin/scripts/complexidade-nova.py` (so complexidade > 10 nova ou aumentada).
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from hook_payload import caminhos_no_repositorio, carregar_payload


class ChecagemImpossivel(Exception):
    """A checagem nao pode ser feita (ferramenta ausente/falhou); vira exit 1."""


def _detect_project_dir() -> str:
    """Raiz do projeto: CLAUDE_PROJECT_DIR, senao a raiz git do cwd, senao o cwd."""
    env_dir = os.environ.get('CLAUDE_PROJECT_DIR')
    if env_dir:
        return str(Path(env_dir).resolve())
    cwd = Path.cwd().resolve()
    try:
        proc = subprocess.run(['git', 'rev-parse', '--show-toplevel'], cwd=cwd, capture_output=True, text=True, check=False)
    except OSError:
        return str(cwd)
    return str(Path(proc.stdout.strip()).resolve()) if proc.returncode == 0 else str(cwd)


PROJECT_DIR = _detect_project_dir()


def ruff_cmd() -> list[str]:
    """Resolve o executavel do ruff (.venv do projeto, .venv do repo do script, PATH ou uv run)."""
    for base in (Path(PROJECT_DIR), Path(__file__).resolve().parents[2]):
        venv_ruff = base / '.venv/bin/ruff'
        if venv_ruff.is_file() and os.access(venv_ruff, os.X_OK):
            return [str(venv_ruff)]
    which_ruff = shutil.which('ruff')
    if which_ruff:
        return [which_ruff]
    which_uv = shutil.which('uv')
    if which_uv:
        return [which_uv, 'run', 'ruff']
    raise ChecagemImpossivel('ruff nao encontrado (.venv/bin/ruff, PATH ou uv)')


def _resolver_arg(arg: str, raiz: Path) -> Path | None:
    """Resolve o argumento pelo cwd e, se nao achar, pela raiz; None se nao for um .py existente."""
    for candidato in (Path(arg), raiz / arg):
        candidato = candidato.resolve()
        if candidato.suffix == '.py' and candidato.is_file():
            return candidato
    return None


def cli_files(args: list[str], raiz: str | Path) -> tuple[list[str], list[str]]:
    """Arquivos .py passados por argumento e os problemas (argumentos que nao resolveram)."""
    raiz_path = Path(raiz).resolve()
    resultado: list[str] = []
    problemas: list[str] = []
    for arg in args:
        candidato = _resolver_arg(arg, raiz_path)
        if candidato is None:
            problemas.append(f'ignorado (nao e um arquivo .py existente): {arg}')
        elif str(candidato) not in resultado:
            resultado.append(str(candidato))
    return resultado, problemas


def _git_nomes(raiz: str | Path, *args: str) -> list[str]:
    """Saida `-z` de um comando git como lista (preserva acentos, sem core.quotePath)."""
    try:
        proc = subprocess.run(['git', *args, '-z'], cwd=raiz, capture_output=True, text=True, check=False)
    except OSError as erro:
        raise ChecagemImpossivel(f'git indisponivel: {erro}') from erro
    if proc.returncode != 0:
        raise ChecagemImpossivel(f'git {args[0]} falhou: {proc.stderr.strip()}')
    return [nome for nome in proc.stdout.split('\0') if nome]


def git_changed_python_files(raiz: str | Path) -> list[str]:
    """Lista arquivos .py modificados (staged/unstaged) vs HEAD ou nao rastreados."""
    arquivos = _git_nomes(raiz, 'diff', '--name-only', 'HEAD')
    arquivos += _git_nomes(raiz, 'ls-files', '--others', '--exclude-standard')
    raiz_path = Path(raiz).resolve()
    resultado: list[str] = []
    for rel in arquivos:
        candidato = (raiz_path / rel).resolve()
        if candidato.suffix == '.py' and candidato.is_file() and str(candidato) not in resultado:
            resultado.append(str(candidato))
    return resultado


def _alvos_do_git() -> tuple[list[str], list[str]]:
    """Modo sem argumentos: alvos do git; lista vazia e problema (nao e aprovacao)."""
    try:
        alvos = git_changed_python_files(PROJECT_DIR)
    except ChecagemImpossivel as erro:
        return [], [str(erro)]
    if not alvos:
        return [], ['nenhum arquivo .py modificado ou novo (vs HEAD) para checar']
    print('Checando: ' + ', '.join(os.path.relpath(alvo, PROJECT_DIR) for alvo in alvos), file=sys.stderr)
    return alvos, []


def files_to_check(args: list[str]) -> tuple[list[str], list[str]]:
    """Arquivos .py a verificar (CLI, payload do hook no stdin ou git) e problemas encontrados."""
    if args:
        return cli_files(args, PROJECT_DIR)

    if sys.stdin is not None and not sys.stdin.isatty():
        entrada = sys.stdin.read()
        if entrada.strip():
            return edited_files(carregar_payload(entrada)), []

    return _alvos_do_git()


def edited_files(payload: dict) -> list[str]:
    """Extrai arquivos Python internos ao repositório do payload do hook."""
    return [str(path) for path in caminhos_no_repositorio(payload, PROJECT_DIR) if path.suffix == '.py']


def edited_file() -> str | None:
    """Mantém a API legada de arquivo único usada por integrações antigas."""
    caminhos = edited_files(carregar_payload(sys.stdin.read()))
    return caminhos[0] if caminhos else None


def added_lines(path: str) -> set[int]:
    """Linhas (lado novo) adicionadas vs HEAD; rastreado sem diff => nenhuma; novo/sem repo => todas."""
    proc = subprocess.run(
        ['git', 'diff', '-U0', '--no-color', 'HEAD', '--', path],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        return parse_added(proc.stdout)
    if proc.returncode == 0 and _rastreado(path):
        return set()
    return all_lines(path)


def _rastreado(path: str) -> bool:
    """O arquivo esta no indice do git (logo, sem diff = nada tocado)."""
    proc = subprocess.run(['git', 'ls-files', '--error-unmatch', '--', path], cwd=PROJECT_DIR, capture_output=True, check=False)
    return proc.returncode == 0


def all_lines(path: str) -> set[int]:
    """Conjunto de todas as linhas do arquivo (1..N)."""
    try:
        n = len(Path(path).read_text().splitlines())
    except OSError:
        return set()
    return set(range(1, n + 1))


def parse_added(diff: str) -> set[int]:
    """Numera as linhas `+` de um diff `-U0`, reiniciando a cada cabecalho @@."""
    lines: set[int] = set()
    cur = 0
    for line in diff.splitlines():
        if line.startswith('@@'):
            cur = hunk_start(line)
        elif line.startswith('+') and not line.startswith('+++'):
            lines.add(cur)
            cur += 1
    return lines


def hunk_start(header: str) -> int:
    """Extrai `start` do trecho `+start[,count]` no cabecalho `@@ ... @@`."""
    plus = header.split('+', 1)[1]
    return int(plus.split(',', 1)[0].split(' ', 1)[0])


def touched_func_lines(path: str, changed: set[int]) -> set[int]:
    """Linha do `def` de cada funcao cujo corpo intersecta `changed`."""
    try:
        tree = ast.parse(Path(path).read_text())
    except OSError, SyntaxError:
        return set()
    out: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            hi = node.end_lineno or node.lineno
            if any(node.lineno <= n <= hi for n in changed):
                out.add(node.lineno)
    return out


def c901_findings(path: str) -> list[tuple[int, str]]:
    """Findings C901 do ruff como (linha_do_def, mensagem); falha do ruff => ChecagemImpossivel."""
    try:
        proc = subprocess.run(
            [
                *ruff_cmd(),
                'check',
                '--select',
                'C901',
                '--config',
                'lint.mccabe.max-complexity=10',
                '--output-format',
                'json',
                path,
            ],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as erro:
        raise ChecagemImpossivel(f'ruff nao executou: {erro}') from erro
    # ruff sai 1 quando ha findings; outro status e erro de execucao/config.
    if proc.returncode not in (0, 1):
        raise ChecagemImpossivel(f'ruff falhou em {path} (exit {proc.returncode}): {proc.stderr.strip()}')
    try:
        data = json.loads(proc.stdout or '[]')
    except ValueError as erro:
        raise ChecagemImpossivel(f'saida do ruff ilegivel em {path}: {erro}') from erro
    return [(d['location']['row'], d['message']) for d in data if d.get('code') == 'C901']


def violacoes(path: str) -> list[str]:
    """Mensagens C901 das funcoes tocadas de um arquivo (vazio se ele nao existe mais)."""
    if not Path(path).is_file():
        return []
    touched = touched_func_lines(path, added_lines(path))
    if not touched:
        return []
    return [msg for row, msg in c901_findings(path) if row in touched]


def main(args: list[str] | None = None) -> int:
    """Exit 2 se alguma funcao tocada exceder C901; 1 se nao deu para checar; 0 se ok."""
    alvos, problemas = files_to_check(sys.argv[1:] if args is None else args)
    offending: list[str] = []
    for path in alvos:
        try:
            offending.extend(violacoes(path))
        except ChecagemImpossivel as erro:
            problemas.append(str(erro))
    for problema in problemas:
        print(f'check_complexity: {problema}', file=sys.stderr)
    if offending:
        print('Complexidade ciclomatica > 10 em funcao(oes) tocada(s) vs HEAD (regra C901).', file=sys.stderr)
        print('Refatore para <= 10:', file=sys.stderr)
        for msg in offending:
            print(f'  - {msg}', file=sys.stderr)
        return 2
    return 1 if problemas else 0


if __name__ == '__main__':
    sys.exit(main())
