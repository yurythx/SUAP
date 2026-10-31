"""Barra complexidade ciclomática > 10 (ruff C901) nova ou maior, sem punir o legado.

Hook do pre-commit. Para cada arquivo, compara as funções acima de 10 na base com as
de agora (por qualname, `Classe.metodo`) e reprova as novas, as que cruzaram o limite
e as legadas já acima de 10 cuja complexidade aumentou. Função legada complexa editada
sem aumentar a complexidade passa (≈1552 no repo).

Base: no commit local, `HEAD` (o pre-commit guarda o não-staged, então a árvore = o
staged); no CI (`--from-ref/--to-ref`), o merge-base dos dois refs. Arquivo renomeado
(`git mv`) é comparado com o caminho antigo.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

LIMITE = 10


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(['git', *args], capture_output=True, text=True, check=False)


def base_ref() -> str:
    """Merge-base de from/to no modo CI; senão HEAD."""
    origem, destino = os.environ.get('PRE_COMMIT_FROM_REF'), os.environ.get('PRE_COMMIT_TO_REF')
    if not (origem and destino):
        return 'HEAD'
    proc = git('merge-base', origem, destino)
    return proc.stdout.strip() if proc.returncode == 0 else origem


def renomeados(base: str) -> dict[str, str]:
    """Mapa caminho_novo -> caminho_antigo dos arquivos renomeados desde a base."""
    saida = git('diff', '-M', '--name-status', base).stdout
    mapa: dict[str, str] = {}
    for linha in saida.splitlines():
        partes = linha.split('\t')
        if partes[0].startswith('R') and len(partes) == 3:
            mapa[partes[2]] = partes[1]
    return mapa


def qualnames(fonte: str) -> dict[int, str]:
    """Linha do `def` -> qualname (`Classe.metodo`, `funcao.interna`)."""
    nomes: dict[int, str] = {}

    def visitar(no: ast.AST, prefixo: str) -> None:
        for filho in ast.iter_child_nodes(no):
            if isinstance(filho, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                nome = f'{prefixo}{filho.name}'
                if not isinstance(filho, ast.ClassDef):
                    nomes[filho.lineno] = nome
                visitar(filho, f'{nome}.')
            else:
                visitar(filho, prefixo)

    try:
        visitar(ast.parse(fonte), '')
    except SyntaxError:
        return {}
    return nomes


def complexas(fonte: str, caminho: str) -> dict[str, list[tuple[int, str]]]:
    """qualname -> (complexidade, mensagem do ruff) de cada função acima do limite, na ordem do arquivo."""
    if not fonte:
        return {}
    proc = subprocess.run(
        [
            'ruff',
            'check',
            '--select',
            'C901',
            '--config',
            f'lint.mccabe.max-complexity={LIMITE}',
            '--output-format',
            'json',
            '--stdin-filename',
            caminho,
            '-',
        ],
        input=fonte,
        capture_output=True,
        text=True,
        check=False,
    )
    nomes = qualnames(fonte)
    achados: dict[str, list[tuple[int, str]]] = {}
    for item in json.loads(proc.stdout or '[]'):
        linha, mensagem = item['location']['row'], item['message']
        valor = int(re.search(r'\((\d+) > ', mensagem).group(1))
        achados.setdefault(nomes.get(linha, f'<linha {linha}>'), []).append((valor, f'{caminho}:{linha}: {mensagem}'))
    return achados


def reprovadas_no_arquivo(caminho: str, base: str, antigo: str) -> list[str]:
    """Mensagens das funções acima do limite que são novas ou ficaram mais complexas que na base.

    Homônimas (`clean` em duas classes têm qualnames distintos; getter/setter não) são
    pareadas pela ordem no arquivo; a sobra de agora conta como nova.
    """
    agora = complexas(Path(caminho).read_text(), caminho)
    antes = complexas(git('show', f'{base}:{antigo}').stdout, caminho)
    reprovadas: list[str] = []
    for nome, ocorrencias in agora.items():
        valores_base = [valor for valor, _ in antes.get(nome, [])]
        for i, (valor, msg) in enumerate(ocorrencias):
            era = valores_base[i] if i < len(valores_base) else None
            if era is None:
                reprovadas.append(msg)
            elif valor > era:
                reprovadas.append(f'{msg} [era {era}]')
    return reprovadas


def main(arquivos: list[str]) -> int:
    base = base_ref()
    mapa = renomeados(base)
    reprovadas = [msg for caminho in arquivos if Path(caminho).is_file() for msg in reprovadas_no_arquivo(caminho, base, mapa.get(caminho, caminho))]
    if not reprovadas:
        return 0
    cabecalho = [
        f'Complexidade ciclomática > {LIMITE} nova ou aumentada (ruff C901).',
        f'Refatore para <= {LIMITE} (extraia helpers, simplifique ramos), ou ao menos não aumente a do legado:',
    ]
    sys.stderr.write('\n'.join([*cabecalho, *(f'  - {msg}' for msg in reprovadas)]) + '\n')
    return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
