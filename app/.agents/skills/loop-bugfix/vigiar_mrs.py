#!/usr/bin/env python3
"""Vigia os MRs em voo do loop de bugfix e imprime uma linha a cada mudança.

Uso: ``vigiar_mrs.py <arquivo_em_voo> [intervalo_s]``. O arquivo tem um iid por linha e é
relido a cada ciclo, então o loop acrescenta e remove MRs sem reiniciar a vigia. Mudança de
estado, de pipeline ou de número de comentários vira uma linha no stdout; erro do ``glab``
vai para o stderr, nunca é engolido. Termina quando todos os MRs listados saem de ``opened``.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

HOST = 'gitlab.ifrn.edu.br'
PROJETO = 'cosinf%2Fsuap'


def ler_iids(arquivo: Path) -> list[str]:
    """Lê os iids em voo, ignorando linhas vazias e comentários."""
    linhas = arquivo.read_text().splitlines() if arquivo.exists() else []
    return [linha.strip().lstrip('!') for linha in linhas if linha.strip() and not linha.startswith('#')]


def estado_do_mr(iid: str) -> tuple[str, str, int] | None:
    """Consulta estado, status do head pipeline e número de comentários humanos do MR."""
    resultado = subprocess.run(
        ['glab', 'api', '--hostname', HOST, f'projects/{PROJETO}/merge_requests/{iid}'], capture_output=True, text=True, check=False
    )
    if resultado.returncode != 0:
        print(f'!{iid}: glab falhou: {resultado.stderr.strip()}', file=sys.stderr, flush=True)
        return None
    mr = json.loads(resultado.stdout)
    pipeline = (mr.get('head_pipeline') or {}).get('status', 'none')
    return mr['state'], pipeline, mr.get('user_notes_count', 0)


def main() -> int:
    """Faz o laço de vigia até todos os MRs listados encerrarem."""
    arquivo = Path(sys.argv[1])
    intervalo = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    vistos: dict[str, tuple[str, str, int]] = {}
    while True:
        iids = ler_iids(arquivo)
        for iid in iids:
            atual = estado_do_mr(iid)
            if atual and atual != vistos.get(iid):
                vistos[iid] = atual
                print(f'!{iid} state={atual[0]} pipeline={atual[1]} comentarios={atual[2]}', flush=True)
        if iids and all(vistos.get(iid, ('opened',))[0] != 'opened' for iid in iids):
            print('todos os MRs em voo encerraram', flush=True)
            return 0
        time.sleep(intervalo)


if __name__ == '__main__':
    raise SystemExit(main())
