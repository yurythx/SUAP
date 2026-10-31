#!/usr/bin/env python
"""Reúne as docs de usuário dos módulos numa árvore que o mkdocs constrói.

Decidido em https://gitlab.ifrn.edu.br/cosinf/suap/-/work_items/16998 e .../17004:

- a fonte mora em ``<modulo>/docs/usuario.md``, junto do código, para entrar no mesmo MR que
  mexe nas telas — o preço é este passo de coleta, porque o ``docs_dir`` do mkdocs é único;
- a navegação é por **área** (``apps.py:area``, 96 apps / 14 áreas), a taxonomia que o
  usuário já vê no menu do SUAP. Não geramos ``nav``: a árvore de diretórios **é** a nav;
- o site ganha uma **página transversal de perfis** (.../17003): cada perfil com as tarefas
  que executa em todos os módulos, mais a ``description`` do ``permissions.yaml`` quando
  existir (só 70 dos 218 nomeados têm);
- a publicação é **manual**, então o site carimba o commit publicado — como a doc antiga
  exibia ``Atualizada em ...``, e pelo mesmo motivo: é o único sinal de que está velho.

Uso::

    python bin/scripts/montar_site_doc.py          # monta site-src/
    mkdocs build                               # site-src/ -> site/
"""

from __future__ import annotations

import os
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import papeis

DESTINO = Path('site-src')
RE_AREA = re.compile(r'^\s*area\s*=\s*[\'"](.+?)[\'"]', re.MULTILINE)
RE_TITULO = re.compile(r'^#\s+(.+?)\s*$', re.MULTILINE)
RE_TAREFA = re.compile(r'^###\s+(?:\d+\.\s*)?(.+?)\s*$', re.MULTILINE)
RE_QUEM_PODE = re.compile(r'^\*\*Quem pode:\*\*\s*(.+?)\s*$', re.MULTILINE)


def ascii_slug(texto: str) -> str:
    """`Gestão de Pessoas` -> `gestao-de-pessoas`."""
    sem_acento = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '-', sem_acento.lower()).strip('-')


def area_do_modulo(modulo: str) -> str:
    """Valor de ``area`` no ``apps.py`` do módulo; `Não definida` quando ausente."""
    apps = Path(modulo, 'apps.py')
    if not apps.exists():
        return 'Não definida'
    casa = RE_AREA.search(apps.read_text(encoding='utf-8'))
    return casa.group(1) if casa else 'Não definida'


def docs_de_usuario() -> list[tuple[str, str, Path]]:
    """``(area, modulo, caminho)`` de cada ``<modulo>/docs/usuario.md``, ordenado."""
    encontrados = []
    for caminho in sorted(Path().glob('*/docs/usuario.md')):
        modulo = caminho.parts[0]
        encontrados.append((area_do_modulo(modulo), modulo, caminho))
    return sorted(encontrados)


def titulo_documento(caminho: Path) -> str:
    """Primeiro H1 do documento; nome do arquivo como fallback."""
    casa = RE_TITULO.search(caminho.read_text(encoding='utf-8'))
    return casa.group(1) if casa else caminho.stem.replace('_', ' ').title()


def perfis_citados(frase: str, conhecidos: set[str]) -> list[str]:
    """Nomes de grupo dentro de uma linha ``**Quem pode:**``.

    A linha nem sempre é uma lista limpa — o subagente escreve prosa ("Comunicador Social **e**
    Coordenador de Comunicação Sistêmico.") e às vezes o papel vem de autorização por dado, que
    não é grupo nenhum. Por isso o casamento é contra o conjunto de grupos que **existem** no
    ``permissions.yaml``: o que não for grupo de verdade simplesmente não entra na página.

    Casa **do nome mais longo para o mais curto, consumindo o trecho**: sem isso "Coordenador
    de Comunicação" leva crédito por toda tarefa de "Coordenador de Comunicação Sistêmico",
    que é prefixado por ele. São 331 grupos e o prefixo comum é a regra, não a exceção.
    """
    restante = frase
    achados = set()
    for grupo in sorted(conhecidos, key=len, reverse=True):
        padrao = re.compile(rf'(?<![^\W_]){re.escape(grupo)}(?![^\W_])')
        if padrao.search(restante):
            achados.add(grupo)
            restante = padrao.sub(' ', restante)
    return sorted(achados)


def tarefas_por_perfil(texto: str, modulo: str, conhecidos: set[str]) -> dict[str, list[str]]:
    """``perfil -> tarefas`` de um documento, lendo os pares ``### Tarefa`` / ``**Quem pode:**``."""
    mapa: dict[str, list[str]] = {}
    for casa in RE_TAREFA.finditer(texto):
        quem = RE_QUEM_PODE.search(texto[casa.end() : casa.end() + 400])
        if not quem:
            continue
        for perfil in perfis_citados(quem.group(1), conhecidos):
            mapa.setdefault(perfil, []).append(f'{modulo}: {casa.group(1)}')
    return mapa


def _sha() -> str:
    """Commit desta montagem.

    ``DOC_COMMIT`` tem precedência porque a montagem roda **dentro do docker build**, e o
    `.dockerignore` exclui `.git` — sem a variável o `git rev-parse` falha e o carimbo, que é
    o único sinal de site velho (#17000), sairia vazio justamente em produção.
    """
    do_ambiente = os.environ.get('DOC_COMMIT', '').strip()
    if do_ambiente:
        return do_ambiente
    achado = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True, check=False)
    return achado.stdout.strip() or '?'


def _carimbo() -> str:
    """Commit e data desta montagem — o único sinal de que o site está velho."""
    return f'Publicado a partir do commit `{_sha()}` em {datetime.now(UTC):%d/%m/%Y %H:%M} UTC.'


def escrever_index(encontrados: list[tuple[str, str, Path]]) -> None:
    """Dados da página inicial, renderizados pelo tema em ``home.html``."""
    areas: dict[str, list[tuple[str, Path]]] = {}
    for area, modulo, caminho in encontrados:
        areas.setdefault(area, []).append((modulo, caminho))

    cards: list[dict[str, str]] = []
    for area, documentos in sorted(areas.items()):
        documentos.sort()
        modulo, _ = documentos[0]
        titulos = ', '.join(titulo_documento(caminho) for _, caminho in documentos)
        cards.append({'nome': area, 'icone': area[0], 'titulos': titulos, 'url': f'{ascii_slug(area)}/{modulo}/'})

    dados = {
        'areas': cards,
        'total_modulos': len(encontrados),
        'total_areas': len(areas),
        'carimbo': _carimbo().replace('`', ''),
    }
    front_matter = json.dumps(dados, ensure_ascii=False, indent=2)
    (DESTINO / 'index.md').write_text(f'---\n{front_matter}\n---\n', encoding='utf-8')


def escrever_perfis(por_perfil: dict[str, list[str]]) -> None:
    """Página transversal: cada perfil, sua descrição e as tarefas que executa."""
    _, descricoes = papeis.indice()
    linhas = [
        '# Perfis de acesso',
        '',
        'O que cada perfil do SUAP pode fazer, reunindo todos os módulos documentados.',
        '',
        'Um perfil listado aqui aparece na linha **Quem pode** de pelo menos uma tarefa. Tarefas cujo acesso é amplo demais',
        'para nomear perfis (mais de cinco grupos) não entram nesta lista — veja a tarefa no documento do módulo.',
        '',
    ]
    for perfil in sorted(por_perfil):
        linhas.append(f'## {perfil}')
        linhas.append('')
        if descricoes.get(perfil):
            linhas += [descricoes[perfil], '']
        linhas += [f'- {tarefa}' for tarefa in sorted(set(por_perfil[perfil]))]
        linhas.append('')
    if not por_perfil:
        linhas += ['*Nenhum módulo documentado ainda.*', '']
    (DESTINO / 'perfis.md').write_text('\n'.join(linhas), encoding='utf-8')


def montar() -> int:
    """Reconstrói ``site-src/`` do zero. Devolve o número de módulos coletados."""
    if DESTINO.exists():
        shutil.rmtree(DESTINO)
    DESTINO.mkdir()

    encontrados = docs_de_usuario()
    _, descricoes = papeis.indice()
    conhecidos = set(descricoes)
    por_perfil: dict[str, list[str]] = {}
    for area, modulo, caminho in encontrados:
        pasta = DESTINO / ascii_slug(area)
        pasta.mkdir(exist_ok=True)
        shutil.copy(caminho, pasta / f'{modulo}.md')
        capturas = caminho.parent / 'usuario'
        if capturas.is_dir():
            shutil.copytree(capturas, pasta / 'usuario', dirs_exist_ok=True)
        for perfil, tarefas in tarefas_por_perfil(caminho.read_text(encoding='utf-8'), titulo_documento(caminho), conhecidos).items():
            por_perfil.setdefault(perfil, []).extend(tarefas)

    escrever_index(encontrados)
    escrever_perfis(por_perfil)
    return len(encontrados)


def main() -> int:
    total = montar()
    perfis = len((DESTINO / 'perfis.md').read_text(encoding='utf-8').split('\n## ')) - 1
    sys.stdout.write(f'{DESTINO}/: {total} módulos coletados, {perfis} perfis na página transversal\n')
    if not total:
        sys.stderr.write('nenhum <modulo>/docs/usuario.md encontrado — o site sairia vazio\n')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
