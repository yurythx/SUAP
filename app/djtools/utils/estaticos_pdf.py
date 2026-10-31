from __future__ import annotations

import base64
import hashlib
import logging
import os
import posixpath
import re
from functools import lru_cache
from typing import NamedTuple

from django.conf import settings
from django.contrib.staticfiles import finders

logger = logging.getLogger(__name__)

# Refs a /static/ dentro de aspas (href, src) ou de url(...) em CSS inline.
REF_ESTATICO = re.compile(r"""["'(]\s*/static/([^"')\s>]+)""")
# Refs dentro de um arquivo CSS: url(...) e @import, inclusive a forma
# `@import url(...)` — sem o `(?:url\()?` o grupo captura o literal "url(" em vez
# do alvo, e a ref aninhada some em silêncio.
REF_CSS = re.compile(r"""(?:url\(|@import\s+(?:url\()?)\s*["']?([^"')\s;]+)""")
EXTERNAS = ('data:', 'http:', 'https:', '//')


class Asset(NamedTuple):
    """Conteúdo de um arquivo estático, pronto para ir na API do suap-pdf."""

    sha256: str
    base64: str


def coletar_assets(*htmls: str | None) -> dict[str, Asset]:
    """Mapeia os `/static/` referenciados nos HTMLs para o conteúdo do arquivo.

    A varredura é feita no HTML já renderizado, então cobre tanto as referências
    dos templates quanto as que vierem no conteúdo escrito pelo usuário. Cada CSS
    coletado é varrido também, para trazer o que ele referencia (fontes, imagens).

    Args:
        htmls: os HTMLs de corpo, cabeçalho e rodapé.

    Returns:
        Dicionário do caminho relativo a `/static/` (sem query) para o `Asset`.
    """
    assets: dict[str, Asset] = {}
    for html in htmls:
        for ref in REF_ESTATICO.findall(html or ''):
            _coletar(_chave(ref), assets)
    return assets


def _chave(ref: str) -> str:
    return posixpath.normpath(ref.split('?', maxsplit=1)[0].split('#', maxsplit=1)[0].lstrip('/'))


def _coletar(chave: str, assets: dict[str, Asset]) -> None:
    if chave in assets or chave.startswith('..') or chave in ('.', '/'):
        return
    caminho = _resolver(chave)
    if not caminho:
        logger.warning('Estático não encontrado para a impressão em PDF: %s', chave)
        return
    try:
        assets[chave] = _ler(caminho, os.path.getmtime(caminho))
    except OSError:
        logger.warning('Estático ilegível para a impressão em PDF: %s', chave)
        return
    if chave.endswith('.css'):
        _coletar_refs_do_css(chave, caminho, assets)


def _coletar_refs_do_css(chave: str, caminho: str, assets: dict[str, Asset]) -> None:
    with open(caminho, encoding='utf-8', errors='ignore') as arquivo:
        css = arquivo.read()
    diretorio = posixpath.dirname(chave)
    for ref in REF_CSS.findall(css):
        ref = ref.strip('\'"')
        if not ref or ref.startswith(EXTERNAS):
            continue
        if ref.startswith('/static/'):
            # Sem o removeprefix a chave sairia como 'static/x.png': o _chave só tira
            # as barras iniciais, não o segmento 'static/', e o arquivo não resolveria.
            _coletar(_chave(ref.removeprefix('/static/')), assets)
        elif not ref.startswith('/'):
            _coletar(_chave(posixpath.join(diretorio, ref)), assets)


def _resolver(chave: str) -> str | None:
    # finders.find acha nos static/ dos apps sem depender do collectstatic, o que
    # faz o mesmo código valer em dev e nos containers web e celery.
    caminho = finders.find(chave)
    if caminho:
        return caminho if isinstance(caminho, str) else caminho[0]
    caminho = os.path.join(settings.STATIC_ROOT, chave)
    return caminho if os.path.isfile(caminho) else None


@lru_cache(maxsize=256)
def _ler(caminho: str, mtime: float) -> Asset:
    # mtime entra na chave do cache só para invalidar quando o arquivo muda.
    with open(caminho, 'rb') as arquivo:
        conteudo = arquivo.read()
    return Asset(hashlib.sha256(conteudo).hexdigest(), base64.b64encode(conteudo).decode())
