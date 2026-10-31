"""Infraestrutura mínima dos adaptadores de hooks do Codex."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType


def raiz_git(cwd: str | Path) -> Path:
    """Retorna a raiz Git; em falha, conserva o diretório recebido."""
    base = Path(cwd).resolve()
    try:
        resultado = subprocess.run(['git', 'rev-parse', '--show-toplevel'], cwd=base, capture_output=True, text=True, check=False)
    except OSError:
        return base
    except subprocess.SubprocessError:
        return base
    return Path(resultado.stdout.strip()).resolve() if resultado.returncode == 0 else base


def carregar_modulo(caminho: Path, nome: str) -> ModuleType:
    """Carrega um núcleo compartilhado por caminho, sem torná-lo pacote público."""
    spec = importlib.util.spec_from_file_location(nome, caminho)
    if spec is None or spec.loader is None:
        raise ImportError(f'não foi possível carregar {caminho}')
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo
