from __future__ import annotations

import difflib
import json
import re

from bs4 import BeautifulSoup, Tag
from django.utils.safestring import SafeString, mark_safe

BLOCOS_HTML = ('p', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'table', 'img')


def _normalizar_texto(texto: str) -> str:
    return re.sub(r'\s+', ' ', texto).strip()


def _descricao_imagem(imagem: Tag) -> str:
    descricao = imagem.get('alt') or imagem.get('title') or 'sem descrição'
    return _normalizar_texto(str(descricao))


def _assinatura_imagem(imagem: Tag) -> str:
    return f'{imagem.get("src", "")}:{_descricao_imagem(imagem)}'


def _imagens(bloco: Tag) -> list[Tag]:
    return [bloco] if bloco.name == 'img' else list(bloco.find_all('img'))


def _assinatura_bloco(bloco: Tag) -> str:
    texto = _normalizar_texto(bloco.get_text(' ', strip=True))
    imagens = '|'.join(_assinatura_imagem(imagem) for imagem in _imagens(bloco))
    return f'{bloco.name}:{texto}:{imagens}'


def _obter_blocos(soup: BeautifulSoup) -> list[Tag]:
    blocos = []
    for bloco in soup.find_all(BLOCOS_HTML):
        if not bloco.find_parent(BLOCOS_HTML):
            blocos.append(bloco)
    return blocos


def _resumir_texto(bloco: Tag) -> str:
    return _normalizar_texto(bloco.get_text(' ', strip=True))


def _registrar_mudancas_imagens(antes: Tag | None, depois: Tag | None, mudancas: list[dict[str, str]]) -> None:
    imagens_antes = [_assinatura_imagem(imagem) for imagem in _imagens(antes)] if antes else []
    imagens_depois = [_assinatura_imagem(imagem) for imagem in _imagens(depois)] if depois else []
    if imagens_antes == imagens_depois:
        return
    if imagens_antes and imagens_depois:
        mudancas.append({'tipo': 'alteracao_imagem', 'texto': 'Imagem alterada.'})
    elif imagens_antes:
        mudancas.append({'tipo': 'remocao_imagem', 'texto': 'Imagem retirada.'})
    else:
        mudancas.append({'tipo': 'adicao_imagem', 'texto': 'Imagem incluída.'})


def _registrar_mudanca_bloco(antes: Tag | None, depois: Tag | None, mudancas: list[dict[str, str]]) -> None:
    texto_antes = _resumir_texto(antes) if antes else ''
    texto_depois = _resumir_texto(depois) if depois else ''
    if texto_antes and texto_depois and texto_antes != texto_depois:
        mudancas.append({'tipo': 'alteracao', 'antes': texto_antes, 'depois': texto_depois})
    elif texto_antes and not texto_depois:
        mudancas.append({'tipo': 'remocao', 'texto': texto_antes})
    elif texto_depois and not texto_antes:
        mudancas.append({'tipo': 'adicao', 'texto': texto_depois})
    _registrar_mudancas_imagens(antes, depois, mudancas)


def _copiar_tag(soup: BeautifulSoup, bloco: Tag) -> Tag:
    copia = BeautifulSoup(str(bloco), 'html.parser').find()
    return copia or soup.new_tag('span')


def _marcar_inclusao(soup: BeautifulSoup, bloco: Tag) -> None:
    marcador = soup.new_tag('ins')
    marcador['class'] = ['diff-addition']
    bloco.wrap(marcador)


def _marcar_substituicao(soup: BeautifulSoup, antes: Tag, depois: Tag) -> None:
    removido = soup.new_tag('del')
    removido['class'] = ['diff-removal']
    removido.append(_copiar_tag(soup, antes))
    depois.insert_before(removido)
    _marcar_inclusao(soup, depois)


def _inserir_remocao(soup: BeautifulSoup, antes: Tag, proximo: Tag | None) -> None:
    removido = soup.new_tag('del')
    removido['class'] = ['diff-removal']
    removido.append(_copiar_tag(soup, antes))
    if proximo:
        proximo.insert_before(removido)
    else:
        soup.append(removido)


def _processar_opcode(
    soup: BeautifulSoup,
    blocos_antes: list[Tag],
    blocos_depois: list[Tag],
    opcode: tuple[str, int, int, int, int],
    mudancas: list[dict[str, str]],
) -> None:
    operacao, i1, i2, j1, j2 = opcode
    if operacao == 'equal':
        return
    pares = max(i2 - i1, j2 - j1)
    for indice in range(pares):
        antes = blocos_antes[i1 + indice] if i1 + indice < i2 else None
        depois = blocos_depois[j1 + indice] if j1 + indice < j2 else None
        _registrar_mudanca_bloco(antes, depois, mudancas)
        if antes and depois:
            _marcar_substituicao(soup, antes, depois)
        elif depois:
            _marcar_inclusao(soup, depois)
        elif antes:
            proximo = blocos_depois[j1] if j1 < len(blocos_depois) else None
            _inserir_remocao(soup, antes, proximo)


def preparar_html_documento(conteudo: str) -> SafeString:
    soup = BeautifulSoup(conteudo or '', 'html.parser')
    for imagem in soup.find_all('img'):
        classes = list(imagem.get('class', []))
        if 'img-fluid' not in classes:
            classes.append('img-fluid')
        imagem['class'] = classes
    return mark_safe(str(soup))


def gerar_comparacao_documentos(original_html: str, retificado_html: str) -> SafeString:
    soup_original = BeautifulSoup(original_html or '', 'html.parser')
    soup_retificado = BeautifulSoup(retificado_html or '', 'html.parser')
    blocos_antes = _obter_blocos(soup_original)
    blocos_depois = _obter_blocos(soup_retificado)
    assinaturas_antes = [_assinatura_bloco(bloco) for bloco in blocos_antes]
    assinaturas_depois = [_assinatura_bloco(bloco) for bloco in blocos_depois]
    mudancas: list[dict[str, str]] = []
    opcodes = difflib.SequenceMatcher(None, assinaturas_antes, assinaturas_depois).get_opcodes()
    for opcode in opcodes:
        _processar_opcode(soup_retificado, blocos_antes, blocos_depois, opcode, mudancas)
    for imagem in soup_retificado.find_all('img'):
        imagem['class'] = [*imagem.get('class', []), 'img-fluid']
    dados = soup_retificado.new_tag('script', id='document-changes-data', type='application/json')
    dados.string = json.dumps(mudancas, ensure_ascii=False).replace('<', '\\u003c')
    soup_retificado.append(dados)
    return mark_safe(str(soup_retificado))
