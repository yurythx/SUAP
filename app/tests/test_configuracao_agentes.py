"""Barra o drift entre os harnesses de agente: o compartilhado vive só em ``.agents/``.

Cada subagente tem um corpo em ``.agents/agents/`` e um registro fino por harness com a mesma
descrição; cada skill é exposta ao Claude Code por symlink; todo hook dos manifestos existe.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[1]
CORPOS = sorted((RAIZ / '.agents/agents').glob('*.md'))
# Colide com a skill embutida /code-review do Claude Code.
SKILLS_SEM_SYMLINK = {'code-review'}


def _frontmatter(arquivo: Path) -> dict:
    return yaml.safe_load(arquivo.read_text().split('---\n', 2)[1])


def _normaliza(texto: str) -> str:
    return ' '.join(texto.split())


def _registros(nome: str) -> dict[str, tuple[str, str]]:
    """Descrição e texto de cada registro do subagente, por harness."""
    claude = RAIZ / f'.claude/agents/{nome}.md'
    opencode = RAIZ / f'.opencode/agent/{nome}.md'
    codex = tomllib.loads((RAIZ / f'.codex/agents/{nome}.toml').read_text())
    return {
        'claude': (_frontmatter(claude)['description'], claude.read_text()),
        'opencode': (_frontmatter(opencode)['description'], opencode.read_text()),
        'codex': (codex['description'], codex['developer_instructions']),
    }


def test_corpo_canonico_tem_frontmatter_neutro() -> None:
    assert CORPOS
    for corpo in CORPOS:
        meta = _frontmatter(corpo)
        assert set(meta) == {'name', 'description'}, f'{corpo.name}: modelo/ferramentas vão no registro de cada harness'
        assert meta['name'] == corpo.stem


def test_todo_harness_registra_cada_subagente_com_a_mesma_descricao() -> None:
    for corpo in CORPOS:
        descricao = _normaliza(_frontmatter(corpo)['description'])
        for harness, (desc, texto) in _registros(corpo.stem).items():
            assert _normaliza(desc) == descricao, f'{harness}/{corpo.stem}: descrição divergiu do corpo'
            assert f'.agents/agents/{corpo.stem}.md' in texto, f'{harness}/{corpo.stem}: não aponta para o corpo'


def test_nenhum_registro_sem_corpo() -> None:
    nomes = {c.stem for c in CORPOS}
    registrados = {
        *(p.stem for p in (RAIZ / '.claude/agents').glob('*.md')),
        *(p.stem for p in (RAIZ / '.opencode/agent').glob('*.md')),
        *(p.stem for p in (RAIZ / '.codex/agents').glob('*.toml')),
    }
    assert registrados <= nomes, f'registro sem corpo em .agents/agents/: {registrados - nomes}'


def test_skills_expostas_ao_claude_por_symlink() -> None:
    skills = {p.name for p in (RAIZ / '.agents/skills').iterdir() if (p / 'SKILL.md').is_file()}
    links = {p.name: p for p in (RAIZ / '.claude/skills').iterdir()}
    assert set(links) == skills - SKILLS_SEM_SYMLINK
    for nome, link in links.items():
        assert link.is_symlink(), nome
        assert link.resolve() == (RAIZ / '.agents/skills' / nome).resolve(), nome


def test_hooks_dos_manifestos_existem() -> None:
    for manifesto in ('.claude/settings.json', '.codex/hooks.json'):
        caminhos = re.findall(r'\.(?:agents|codex)/hooks/\w+\.py', (RAIZ / manifesto).read_text())
        assert caminhos, manifesto
        for caminho in caminhos:
            assert (RAIZ / caminho).is_file(), f'{manifesto} aponta para {caminho}, que não existe'


def test_hooks_do_antigravity_existem() -> None:
    # O Antigravity resolve o `command` relativo a `.agents/`.
    manifesto = json.loads((RAIZ / '.agents/hooks.json').read_text())
    comandos = [h['command'] for grupo in manifesto.values() for hooks in grupo.values() for h in hooks]
    assert comandos
    for comando in comandos:
        assert (RAIZ / '.agents' / comando).resolve().is_file(), f'.agents/hooks.json aponta para {comando}, que não existe'
