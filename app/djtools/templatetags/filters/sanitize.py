from __future__ import annotations

import logging
import re
from textwrap import wrap

from django import template
from django.utils.html import escape
from django.utils.safestring import SafeString, mark_safe
from lxml import html
from lxml.html import clean

register = template.Library()
logger = logging.getLogger(__name__)

MARCADOR_QUEBRA_PAGINA = '<div class="page-break"></div>'
# wkhtmltopdf quebra se não remover urls https
# conteudo = re.sub(r'https:\/{2}[\d\w-]+(\.[\d\w-]+)*(?:(?:\/[^\s/]*))*', '', conteudo) # remove demais string demais
URL_HTTPS_EM_CSS = re.compile(r'(url\(\"*\'*https:\/\/)(\s)*(www\.)?(\s)*((\w|\s|\-)+\.)*([\w\-\s]+\/)*([\w\-\.]+)((\?)?[\w\s]*=\s*[\w\%&]*)*')


def _substituir_quebras_pagina_legadas(conteudo: str) -> str:
    return re.sub(r'<!--\s*pagebreak\s*-->', MARCADOR_QUEBRA_PAGINA, conteudo, flags=re.IGNORECASE)


def _corrigir_tabelas_sem_corpo(conteudo: str) -> str:
    arvore = html.fromstring(conteudo)
    for cabecalho in arvore.xpath('descendant-or-self::table[thead//td and not(tbody)]/thead'):
        cabecalho.tag = 'tbody'
    return html.tostring(arvore, encoding='unicode')


@register.filter
def sanitize(obj: object, skip: str | None = None) -> SafeString:
    """
    Instances cleans the document of each of the possible offending
    elements.  The cleaning is controlled by attributes; you can
    override attributes in a subclass, or set them in the constructor.

    ``scripts``:
        Removes any ``<script>`` tags.

    ``javascript``:
        Removes any Javascript, like an ``onclick`` attribute. Also removes stylesheets
        as they could contain Javascript.

    ``comments``:
        Removes any comments.

    ``style``:
        Removes any style tags.

    ``inline_style``
        Removes any style attributes.  Defaults to the value of the ``style`` option.

    ``links``:
        Removes any ``<link>`` tags

    ``meta``:
        Removes any ``<meta>`` tags

    ``page_structure``:
        Structural parts of a page: ``<head>``, ``<html>``, ``<title>``.

    ``processing_instructions``:
        Removes any processing instructions.

    ``embedded``:
        Removes any embedded objects (flash, iframes)

    ``frames``:
        Removes any frame-related tags

    ``forms``:
        Removes any form tags

    ``annoying_tags``:
        Tags that aren't *wrong*, but are annoying.  ``<blink>`` and ``<marquee>``

    ``remove_tags``:
        A list of tags to remove.  Only the tags will be removed,
        their content will get pulled up into the parent tag.

    ``kill_tags``:
        A list of tags to kill.  Killing also removes the tag's content,
        i.e. the whole subtree, not just the tag itself.

    ``allow_tags``:
        A list of tags to include (default include all).

    ``remove_unknown_tags``:
        Remove any tags that aren't standard parts of HTML.

    ``safe_attrs_only``:
        If true, only include 'safe' attributes (specifically the list
        from the feedparser HTML sanitisation web site).

    ``safe_attrs``:
        A set of attribute names to override the default list of attributes
        considered 'safe' (when safe_attrs_only=True).

    ``add_nofollow``:
        If true, then any <a> tags will have ``rel="nofollow"`` added to them.

    ``host_whitelist``:
        A list or set of hosts that you can use for embedded content
        (for content like ``<object>``, ``<link rel="stylesheet">``, etc).
        You can also implement/override the method
        ``allow_embedded_url(el, url)`` or ``allow_element(el)`` to
        implement more complex rules for what can be embedded.
        Anything that passes this test will be shown, regardless of
        the value of (for instance) ``embedded``.

        Note that this parameter might not work as intended if you do not
        make the links absolute before doing the cleaning.

        Note that you may also need to set ``whitelist_tags``.

    ``whitelist_tags``:
        A set of tags that can be included with ``host_whitelist``.
        The default is ``iframe`` and ``embed``; you may wish to
        include other tags like ``script``, or you may want to
        implement ``allow_embedded_url`` for more control.  Set to None to
        include all tags.

    This modifies the document *in place*.

    Se a limpeza falhar (ex.: o lxml recusa uma string com declaração XML de ``encoding``), o conteúdo é devolvido
    escapado, nunca cru: o HTML que não pôde ser limpo não pode chegar à página nem ao PDF.
    """
    conteudo = '' if obj is None else str(obj)
    try:
        if skip == 'processo_eletronico':
            return mark_safe(_limpar_processo_eletronico(conteudo))
        return mark_safe(clean.Cleaner().clean_html(conteudo))
    except Exception:
        # O lxml também falha em conteúdo vazio ("Document is empty"), que não é erro de quem chama.
        if conteudo.strip():
            logger.exception('Falha ao sanitizar HTML; o conteúdo foi devolvido escapado.')
        return escape(conteudo)


def _limpar_processo_eletronico(conteudo: str) -> str:
    cleaner = clean.Cleaner(safe_attrs=html.defs.safe_attrs | {'style'})
    conteudo = cleaner.clean_html(_substituir_quebras_pagina_legadas(conteudo))
    conteudo = _corrigir_tabelas_sem_corpo(conteudo)
    return URL_HTTPS_EM_CSS.sub('', conteudo)


@register.filter
def force_wordwrap(obj, size):
    words = obj.split(' ')
    result = []
    for word in words:
        result = result + wrap(word, size)
    return ' '.join(result)
