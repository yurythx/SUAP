"""Identifica o layout de um arquivo do extrator comparando seu .REF com os de `rh/refs`.

O nome do arquivo (ex.: 676422.REF) não diz o que ele contém; o conteúdo do .REF, sim.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from django.conf import settings

PASTA_REFS = os.path.join(settings.BASE_DIR, 'rh', 'refs')


# Para que serve: a preparação precisa guardar, por arquivo, tanto o layout reconhecido quanto a
# explicação de por que não foi reconhecido, que é o que o operador vê na tela para investigar.
@dataclass(frozen=True)
class Identificacao:
    """Resultado de identificar um arquivo do extrator pelo conteúdo do seu `.REF`.

    Attributes:
        layout: Nome do layout reconhecido, ou `None` se nenhum `.REF` de referência bateu.
        diagnostico: Texto explicando por que não houve correspondência (só preenchido quando
            `layout` é `None`); ver `_diagnosticar`.
    """

    layout: str | None
    diagnostico: str = ''


# Para que serve: carrega uma vez, por zip recebido, os `.REF` conhecidos, em vez de reler o disco
# a cada arquivo identificado. Acrescentar um layout novo é só pôr o `.REF` dele em `rh/refs`.
def carregar_refs(pasta: str = PASTA_REFS) -> dict[str, str]:
    """Lê todos os `.REF` de referência de `pasta` (padrão: `rh/refs`).

    Args:
        pasta: Diretório com os arquivos `.REF` de referência, um por layout conhecido.

    Returns:
        Nome do layout (nome do arquivo sem a extensão `.REF`) -> conteúdo do arquivo.
    """
    refs = {}
    for nome in sorted(os.listdir(pasta)):
        if nome.endswith('.REF'):
            with open(os.path.join(pasta, nome), encoding='utf-8') as arquivo:
                refs[nome.removesuffix('.REF')] = arquivo.read()
    return refs


# Para que serve: os arquivos do extrator vêm com nomes numéricos (ex.: 676422.TXT) que não dizem o
# que contêm; sem isto o operador teria de renomear ou apontar cada layout na mão, e um layout
# alterado pelo SIAPE passaria despercebido até quebrar a importação.
def identificar(conteudo_ref: str, refs: Mapping[str, str]) -> Identificacao:
    """Identifica o layout de um arquivo comparando seu `.REF` (normalizado) com os de referência.

    Args:
        conteudo_ref: Conteúdo do `.REF` do arquivo a identificar.
        refs: Nome do layout -> conteúdo do `.REF` de referência, como devolvido por `carregar_refs`.

    Returns:
        `Identificacao` com o nome do primeiro layout (na ordem de `refs`) cujo `.REF` é idêntico
        após remover todo espaço em branco, ou com `layout=None` e um diagnóstico quando nenhum é.
    """
    normalizado = _normalizar(conteudo_ref)
    for nome, conteudo in refs.items():
        if _normalizar(conteudo) == normalizado:
            return Identificacao(nome)
    return Identificacao(None, _diagnosticar(conteudo_ref, refs))


def _normalizar(conteudo: str) -> str:
    """Remove todo espaço em branco, para comparar dois `.REF` ignorando diferenças de formatação."""
    return ''.join(conteudo.split())


def _campos(conteudo: str) -> set[str]:
    """Primeiro token de cada linha não vazia do `.REF` (o nome de cada campo do layout)."""
    return {linha.split()[0] for linha in conteudo.splitlines() if linha.strip()}


def _semelhanca(campos: set[str], outros: set[str]) -> float:
    """Índice de Jaccard entre dois conjuntos de campos (0 sem nenhum em comum, 1 idênticos)."""
    return len(campos & outros) / len(campos | outros) if campos | outros else 0.0


def _diagnosticar(conteudo_ref: str, refs: Mapping[str, str]) -> str:
    """Monta uma explicação legível de por que o `.REF` não bateu com nenhum layout conhecido.

    Aponta o layout de referência mais parecido (por semelhança de campos) e a diferença de campos
    entre os dois, para ajudar a investigar um layout novo ou desatualizado.

    Args:
        conteudo_ref: Conteúdo do `.REF` que não foi reconhecido.
        refs: Nome do layout -> conteúdo do `.REF` de referência.

    Returns:
        Um texto com o layout mais próximo e os campos a mais/a menos em relação a ele, ou uma
        mensagem genérica quando não há campos ou referências para comparar.
    """
    campos = _campos(conteudo_ref)
    if not campos or not refs:
        return 'Arquivo de referência vazio ou sem layouts conhecidos para comparar.'
    mais_proximo = max(refs, key=lambda nome: _semelhanca(campos, _campos(refs[nome])))
    campos_ref = _campos(refs[mais_proximo])
    a_mais, a_menos = sorted(campos - campos_ref), sorted(campos_ref - campos)
    partes = [f'Layout mais próximo: {mais_proximo} ({_semelhanca(campos, campos_ref):.0%} dos campos em comum).']
    if a_mais:
        partes.append('Campos a mais: ' + ', '.join(a_mais) + '.')
    if a_menos:
        partes.append('Campos a menos: ' + ', '.join(a_menos) + '.')
    if not a_mais and not a_menos:
        partes.append('Mesmos campos, com tipo, tamanho ou ordem diferentes.')
    return ' '.join(partes)
