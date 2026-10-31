"""Normaliza caminhos recebidos nos payloads de hooks dos agentes."""

from __future__ import annotations

import re
from pathlib import Path

_CABECALHO_CODEX = re.compile(r'^\*\*\* (?:Add|Update|Delete) File: (.+)$')
_MOVER_CODEX = re.compile(r'^\*\*\* Move to: (.+)$')


def carregar_payload(entrada: str) -> dict:
    """Converte a entrada JSON do hook em dicionário; entrada inválida vira vazio."""
    import json

    try:
        payload = json.loads(entrada)
    except json.JSONDecodeError:
        return {}
    except TypeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def caminhos_do_patch(patch: str) -> list[str]:
    """Extrai caminhos estruturais de patches Codex V4A e unified diff."""
    caminhos: list[str] = []
    for linha in patch.splitlines():
        caminho = _caminho_codex(linha) or _caminho_unified(linha)
        if caminho and caminho not in caminhos:
            caminhos.append(caminho)
    return caminhos


def _caminho_codex(linha: str) -> str | None:
    encontrado = _CABECALHO_CODEX.fullmatch(linha) or _MOVER_CODEX.fullmatch(linha)
    return encontrado.group(1).strip() if encontrado else None


def _caminho_unified(linha: str) -> str | None:
    if not linha.startswith(('--- ', '+++ ')):
        return None
    caminho = linha[4:].split('\t', 1)[0].strip()
    if caminho == '/dev/null':
        return None
    return caminho.removeprefix('a/').removeprefix('b/')


def caminhos_do_payload(payload: dict) -> list[str]:
    """Lê o caminho legado ou todos os caminhos do comando ``apply_patch``."""
    entrada = payload.get('tool_input') or {}
    if not isinstance(entrada, dict):
        return []
    caminho = entrada.get('file_path')
    if isinstance(caminho, str) and caminho:
        return [caminho]
    comando = entrada.get('command')
    return caminhos_do_patch(comando) if isinstance(comando, str) else []


def caminhos_no_repositorio(payload: dict, raiz: str | Path) -> list[Path]:
    """Resolve caminhos do payload e descarta entradas fora do repositório."""
    raiz_resolvida = Path(raiz).resolve()
    cwd = _cwd_confiavel(payload, raiz_resolvida)
    caminhos: list[Path] = []
    for caminho in caminhos_do_payload(payload):
        candidato = Path(caminho)
        resolvido = candidato.resolve() if candidato.is_absolute() else (cwd / candidato).resolve()
        if resolvido.is_relative_to(raiz_resolvida) and resolvido not in caminhos:
            caminhos.append(resolvido)
    return caminhos


def _cwd_confiavel(payload: dict, raiz: Path) -> Path:
    cwd = payload.get('cwd')
    if not isinstance(cwd, str):
        return raiz
    resolvido = Path(cwd).resolve()
    return resolvido if resolvido.is_relative_to(raiz) else raiz
