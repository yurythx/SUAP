#!/usr/bin/env -S uv run --quiet python3
"""Regressões dos payloads Claude/OpenCode/Codex para o gate C901."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

_SPEC = importlib.util.spec_from_file_location('check_complexity', Path(__file__).with_name('check_complexity.py'))
hook = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(hook)


def _payload(command: str) -> dict:
    return {'cwd': hook.PROJECT_DIR, 'tool_input': {'command': command}}


def _extracao() -> None:
    legado = {'tool_input': {'file_path': 'comum/utils.py'}}
    assert hook.edited_files(legado) == [str(Path(hook.PROJECT_DIR, 'comum/utils.py').resolve())]

    multiplo = _payload('*** Begin Patch\n*** Update File: comum/a.py\n*** Update File: comum/nota.txt\n*** Add File: djtools/b.py\n*** End Patch')
    assert hook.edited_files(multiplo) == [
        str(Path(hook.PROJECT_DIR, 'comum/a.py').resolve()),
        str(Path(hook.PROJECT_DIR, 'djtools/b.py').resolve()),
    ]

    renomeado = _payload('*** Update File: comum/antigo.py\n*** Move to: comum/novo.py')
    assert hook.edited_files(renomeado) == [
        str(Path(hook.PROJECT_DIR, 'comum/antigo.py').resolve()),
        str(Path(hook.PROJECT_DIR, 'comum/novo.py').resolve()),
    ]
    assert hook.edited_files(_payload('patch inválido sem cabeçalho')) == []
    assert hook.edited_files({'cwd': '/', 'tool_input': {'file_path': '/tmp/fora.py'}}) == []


def _unified_diff() -> None:
    payload = _payload(
        'diff --git a/comum/a.py b/comum/a.py\n--- a/comum/a.py\n+++ b/comum/a.py\n'
        '@@ -1 +1 @@\n-x\n+y\n'
        'diff --git a/velho.py b/novo.py\n--- a/velho.py\n+++ b/novo.py\n'
        'diff --git a/removido.py b/removido.py\n--- a/removido.py\n+++ /dev/null'
    )
    assert hook.edited_files(payload) == [
        str(Path(hook.PROJECT_DIR, 'comum/a.py').resolve()),
        str(Path(hook.PROJECT_DIR, 'velho.py').resolve()),
        str(Path(hook.PROJECT_DIR, 'novo.py').resolve()),
        str(Path(hook.PROJECT_DIR, 'removido.py').resolve()),
    ]


def _complexidade_tocada() -> None:
    fonte = """def legada(valor):
    if valor:
        return 1
    return 0

def tocada(valor):
    if valor:
        return 1
    return 0"""
    with tempfile.TemporaryDirectory() as diretorio:
        caminho = Path(diretorio, 'exemplo.py')
        caminho.write_text(fonte)
        assert hook.touched_func_lines(str(caminho), {7}) == {6}
        with (
            patch.object(hook, 'PROJECT_DIR', diretorio),
            patch.object(hook, 'edited_files', return_value=[str(caminho)]),
            patch.object(hook, 'added_lines', return_value={7}),
            patch.object(hook, 'c901_findings', return_value=[(1, 'legada é complexa'), (6, 'tocada é complexa')]),
            patch.object(hook.sys, 'stdin', io.StringIO('{}')),
            redirect_stderr(io.StringIO()) as erro,
        ):
            assert hook.main() == 2
            assert 'tocada é complexa' in erro.getvalue()
            assert 'legada é complexa' not in erro.getvalue()


def _cli_argumentos() -> None:
    with tempfile.TemporaryDirectory() as diretorio:
        arq1 = Path(diretorio, 'arq1.py')
        arq1.write_text('x = 1\n')
        arq2 = Path(diretorio, 'arq2.txt')
        arq2.write_text('x = 1\n')
        # Apenas .py existentes sao alvos; o resto vira problema (exit 1), nao some
        resolvidos, problemas = hook.cli_files([str(arq1), str(arq2), 'nao_existe.py'], diretorio)
        assert resolvidos == [str(arq1.resolve())]
        assert len(problemas) == 2


def _files_to_check_despacho() -> None:
    with tempfile.TemporaryDirectory() as diretorio:
        arq = Path(diretorio, 'teste.py')
        arq.write_text('x = 1\n')
        with patch.object(hook, 'PROJECT_DIR', diretorio):
            # Prioridade 1: argumentos CLI
            assert hook.files_to_check([str(arq)]) == ([str(arq.resolve())], [])

            # Prioridade 2: payload JSON em stdin (quando não for tty)
            payload = '{"tool_input": {"file_path": "teste.py"}}'
            with patch.object(hook.sys, 'stdin', io.StringIO(payload)):
                assert hook.files_to_check([]) == ([str(arq.resolve())], [])

            # Prioridade 3: fallback git quando stdin vazio / tty
            with (
                patch.object(hook.sys, 'stdin', io.StringIO('')),
                patch.object(hook, 'git_changed_python_files', return_value=[str(arq.resolve())]),
                redirect_stderr(io.StringIO()),
            ):
                assert hook.files_to_check([]) == ([str(arq.resolve())], [])


_COMPLEXA = """def funcao_complexa(v):
    if v == 1: return 1
    elif v == 2: return 2
    elif v == 3: return 3
    elif v == 4: return 4
    elif v == 5: return 5
    elif v == 6: return 6
    elif v == 7: return 7
    elif v == 8: return 8
    elif v == 9: return 9
    elif v == 10: return 10
    return 0
"""


def _main_cli_bloqueio() -> None:
    fonte = _COMPLEXA
    with tempfile.TemporaryDirectory() as diretorio:
        caminho = Path(diretorio, 'complexo.py')
        caminho.write_text(fonte)
        with (
            patch.object(hook, 'PROJECT_DIR', diretorio),
            patch.object(hook, 'added_lines', return_value=set(range(1, 15))),
            redirect_stderr(io.StringIO()) as erro,
        ):
            # Chamada via CLI passando argumento diretamente
            assert hook.main([str(caminho)]) == 2
            assert 'funcao_complexa' in erro.getvalue()


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ['git', '-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'commit.gpgsign=false', *args], cwd=repo, check=True, capture_output=True
    )


@contextlib.contextmanager
def _repo():
    """Repositorio git temporario com um commit e o hook apontando para ele."""
    with tempfile.TemporaryDirectory() as diretorio:
        repo = Path(diretorio).resolve()
        _git(repo, 'init', '-q')
        (repo / 'legado.py').write_text(_COMPLEXA)
        (repo / 'some.py').write_text('x = 1\n')
        (repo / 'pacote').mkdir()
        (repo / 'pacote/mod.py').write_text('x = 1\n')
        _git(repo, 'add', '.')
        _git(repo, 'commit', '-q', '-m', 'base')
        with patch.object(hook, 'PROJECT_DIR', str(repo)), patch.object(hook.sys, 'stdin', io.StringIO('')):
            yield repo


def _rodar(args: list[str]) -> tuple[int, str]:
    with redirect_stderr(io.StringIO()) as erro:
        return hook.main(args), erro.getvalue()


def _modo_git() -> None:
    with _repo() as repo:
        # Arvore limpa: nada para checar nao e aprovacao
        status, erro = _rodar([])
        assert status == 1
        assert 'nenhum arquivo .py' in erro

        (repo / 'pacote/mod.py').write_text('x = 2\n')
        (repo / 'some.py').unlink()
        (repo / 'notas.txt').write_text('x')
        (repo / 'modulo_ação.py').write_text(_COMPLEXA)
        assert hook.git_changed_python_files(repo) == [str(repo / 'pacote/mod.py'), str(repo / 'modulo_ação.py')]

        status, erro = _rodar([])
        assert status == 2
        assert 'funcao_complexa' in erro
        assert 'modulo_ação.py' in erro

        # fd 0 fechado: sys.stdin None cai no modo git em vez de AttributeError
        with patch.object(hook.sys, 'stdin', None):
            assert _rodar([])[0] == 2


def _modo_pontual() -> None:
    with _repo() as repo:
        # Rastreado sem diff: nenhuma funcao tocada, mesmo com legado complexo
        assert _rodar([str(repo / 'legado.py')])[0] == 0

        (repo / 'pacote/novo.py').write_text(_COMPLEXA)
        anterior = Path.cwd()
        os.chdir(repo / 'pacote')
        try:
            # Relativo ao cwd, nao a raiz; o que nao resolve e avisado e da exit 1
            assert _rodar(['novo.py'])[0] == 2
            status, erro = _rodar(['mod.py', 'naoexiste.py'])
            assert status == 1
            assert 'naoexiste.py' in erro
        finally:
            os.chdir(anterior)


def _ruff_ausente() -> None:
    with _repo() as repo:
        (repo / 'novo.py').write_text(_COMPLEXA)
        with (
            patch.object(hook.os, 'access', return_value=False),
            patch.object(hook.shutil, 'which', return_value=None),
        ):
            status, erro = _rodar([str(repo / 'novo.py')])
        assert status == 1
        assert 'ruff nao encontrado' in erro


def _adaptador_antigravity() -> None:
    adaptador = Path(__file__).resolve().parents[2] / '.agents/hooks/antigravity_check_complexity.py'
    with _repo() as repo:
        payload = json.dumps({'workspacePaths': [str(repo)], 'terminationReason': 'model_stop', 'fullyIdle': True})

        def parar() -> dict:
            proc = subprocess.run([sys.executable, str(adaptador)], input=payload, capture_output=True, text=True, check=True)
            return json.loads(proc.stdout)

        # Arvore limpa (exit 1 do nucleo) deixa o agente parar
        assert parar()['decision'] != 'continue'
        (repo / 'novo.py').write_text(_COMPLEXA)
        resposta = parar()
        assert resposta['decision'] == 'continue'
        assert 'funcao_complexa' in resposta['reason']


def main() -> None:
    _extracao()
    _unified_diff()
    _complexidade_tocada()
    _cli_argumentos()
    _files_to_check_despacho()
    _main_cli_bloqueio()
    _modo_git()
    _modo_pontual()
    _ruff_ausente()
    _adaptador_antigravity()
    print('ok')


if __name__ == '__main__':
    main()
