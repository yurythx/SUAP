"""Coleta de conteúdo de recursos: download com paginação e leitura tabular.

Camada de baixo nível, deliberadamente ignorante de PDA, LAI e CKAN: recebe uma URL ou um texto
e devolve bytes ou colunas/linhas. É consumida tanto pela rotina de atualização automática quanto
pela prévia da tela de deliberação do LAI, para que exista uma única régua sobre "quais são as
colunas deste arquivo".
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from itertools import islice

from dados_abertos.enums import FormatoRecurso
from djtools.utils import requests

# Teto de segurança para a paginação: um dataset aberto é grande, mas 500 páginas de 100 já são
# 50 mil registros — além disso é mais provável ser defeito do servidor do que volume legítimo.
MAX_PAGINAS = 500


class ColetaTruncada(RuntimeError):
    """A paginação passou do teto: o conteúdo lido não é o conjunto completo."""


@dataclass(frozen=True)
class Coletado:
    """Conteúdo baixado de uma URL, já com a paginação resolvida."""

    conteudo: bytes
    content_type: str
    paginas: int


@dataclass(frozen=True)
class Tabular:
    """Leitura de um conteúdo CSV/JSON em colunas e linhas."""

    colunas: list[str]
    linhas: list[list[str]]
    erro: str | None


def _envelope(conteudo: bytes) -> dict | None:
    """Devolve o envelope de paginação do djtools, ou ``None`` se o conteúdo não for um.

    O reconhecimento é estrutural (``results`` lista + chave ``next``) porque ``RecursoDados.url``
    pode apontar para qualquer lugar: um CSV externo não deve ser interpretado como página.
    """
    try:
        dados = json.loads(conteudo)
    except ValueError:
        return None
    if isinstance(dados, dict) and isinstance(dados.get('results'), list) and 'next' in dados:
        return dados
    return None


def baixar(url: str, *, timeout: int = 30) -> Coletado:
    """Baixa a URL e, quando ela responde paginado, percorre as páginas e concatena os registros.

    A API do SUAP pagina toda resposta ``list[...]`` em 100 itens (``djtools.ninja.pagination``),
    então um GET único publicaria no CKAN a primeira página embrulhada em ``{"results": ...}``.
    Aqui o envelope é desfeito e o arquivo final é um array JSON com o conjunto completo.

    Args:
        url: Endereço do recurso.
        timeout: Tempo limite de cada requisição, em segundos.

    Returns:
        Coletado: Conteúdo final, tipo MIME da primeira resposta e número de páginas lidas.

    Raises:
        ColetaTruncada: Quando a paginação passa de ``MAX_PAGINAS`` — o conteúdo lido seria um
            recorte com aparência de conjunto completo.
    """
    resposta = requests.get(url, timeout=timeout)
    resposta.raise_for_status()
    content_type = resposta.headers.get('Content-Type', '')

    envelope = _envelope(resposta.content)
    if envelope is None:
        return Coletado(conteudo=resposta.content, content_type=content_type, paginas=1)

    registros = list(envelope['results'])
    visitadas = {url}
    proxima = envelope.get('next')
    while proxima and proxima not in visitadas:
        if len(visitadas) >= MAX_PAGINAS:
            # Parar aqui e devolver o que deu tempo publicaria um recorte com cara de conjunto
            # completo. Falhar alto vira FALHA_DOWNLOAD, aparece no histórico e cobra alguém.
            raise ColetaTruncada(f'A coleta passou do teto de {MAX_PAGINAS} páginas em {url}. O conteúdo não está completo e nada foi publicado.')
        visitadas.add(proxima)
        resposta = requests.get(proxima, timeout=timeout)
        resposta.raise_for_status()
        pagina = _envelope(resposta.content)
        if pagina is None:
            break
        registros.extend(pagina['results'])
        proxima = pagina.get('next')

    return Coletado(
        conteudo=json.dumps(registros, ensure_ascii=False).encode(),
        content_type=content_type,
        paginas=len(visitadas),
    )


def _detectar_delimitador(cabecalho: str) -> str:
    """Heurística simples de delimitador CSV: ``;`` se predominar sobre ``,`` (comum no Brasil)."""
    return ';' if cabecalho.count(';') > cabecalho.count(',') else ','


def _ler_csv(texto: str, limite: int | None) -> Tabular:
    primeira_linha = texto.splitlines()[0] if texto.strip() else ''
    leitor = csv.reader(io.StringIO(texto), delimiter=_detectar_delimitador(primeira_linha))
    linhas_raw = list(islice(leitor, limite + 1)) if limite is not None else list(leitor)
    if not linhas_raw:
        return Tabular(colunas=[], linhas=[], erro='Arquivo vazio.')
    return Tabular(colunas=linhas_raw[0], linhas=linhas_raw[1:], erro=None)


def _registros_json(dados: object) -> list:
    """Extrai a lista de registros: a própria lista, a primeira lista dentro de um objeto, ou o
    próprio objeto como registro único.

    O último caso é o endpoint que responde um objeto plano em vez de uma coleção — como
    ``/ensino/estatistica/alunos_geral/``, que declara ``response=EstatisticaAlunoGeralSchema``.
    É uma linha só, mas é uma linha: tratá-lo como "sem registros" deixava a prévia do LAI vazia
    para um recurso que tem dados. Objeto sem chave alguma continua sendo nada.
    """
    if isinstance(dados, list):
        return dados
    if isinstance(dados, dict):
        for valor in dados.values():
            if isinstance(valor, list):
                return valor
        return [dados] if dados else []
    return []


def _ler_json(texto: str, limite: int | None) -> Tabular:
    try:
        dados = json.loads(texto)
    except ValueError:
        return Tabular(colunas=[], linhas=[], erro='JSON inválido.')
    registros = _registros_json(dados)
    if not registros:
        return Tabular(colunas=[], linhas=[], erro='Sem registros.')
    primeiro = registros[0]
    if not isinstance(primeiro, dict):
        return Tabular(colunas=['valor'], linhas=[[str(reg)] for reg in registros[:limite]], erro=None)
    colunas = list(primeiro.keys())
    linhas = [[str(reg.get(coluna, '')) for coluna in colunas] for reg in registros[:limite]]
    return Tabular(colunas=colunas, linhas=linhas, erro=None)


def ler_tabular(texto: str, formato: str = '', limite: int | None = None) -> Tabular:
    """Lê um conteúdo CSV ou JSON em colunas e linhas. Nunca lança: erro vira ``Tabular.erro``.

    Args:
        texto: Conteúdo do recurso, já decodificado.
        formato: ``FormatoRecurso`` declarado no recurso; quando vazio, o formato é inferido.
        limite: Número máximo de linhas a ler (``None`` lê tudo). As colunas **nunca** são
            truncadas — quem exibe é que recorta, porque a lista completa é o esquema do recurso.

    Returns:
        Tabular: Colunas, linhas e o erro de leitura, quando houver.
    """
    if (formato or '').upper() == FormatoRecurso.JSON or texto.lstrip()[:1] in ('[', '{'):
        return _ler_json(texto, limite)
    return _ler_csv(texto, limite)
