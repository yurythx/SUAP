"""Importação das revistas RPI do INPI, compartilhada pelos comandos ``importar_rpi*``.

O ``_`` no nome impede o Django de tratar este módulo como comando.

Cada revista é um zip com um TXT em blocos: ``(Cd) <código do despacho>`` seguido das linhas do
processo (``(21)`` número, ``(22)`` data de depósito, ``(54)`` título, ``(71)``/``(73)`` titulares,
``(72)`` inventores...). Os comandos diferem só nas tags de cada campo, no jeito de baixar e ler o
arquivo e na chave do despacho — diferenças mantidas aqui como opções de ``Importacao``.
"""

from __future__ import annotations

import os
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import datetime
from io import BytesIO
from pathlib import Path

import mechanicalsoup
from django.conf import settings

from comum.models import Configuracao
from djtools.utils import requests
from pesquisa.models import PropriedadeIntelectual, PublicacaoPropriedadeIntelectual, RegistroPropriedadeIntelectual

URL_REVISTAS = 'http://revistas.inpi.gov.br/rpi/'
NOME_PADRAO_INSTITUICAO = 'INSTITUTO FEDERAL DE EDUCAÇÃO, CIÊNCIA E TECNOLOGIA DO RIO GRANDE DO NORTE'
# Grafias do nome da instituição encontradas nos titulares das revistas, além do nome configurado.
GRAFIAS_INSTITUICAO = (
    'INSTITUTO FEDERAL DE EDUCAÇÃO, CIÊNCIA E TECNOLOGIA DO RN',
    'INSTITUTO FEDERAL DE EDUCAÇÃO , CIÊNCIA E TECNOLOGIA DO RIO GRANDE DO NORTE',
    'INSTITUTO FEDERAL DE EDUCACAO, CIENCIA E TECNOLOGIA DO RIO GRANDE DO NORTE',
    'INSTITUTO FEDERAL DE CIÊNCIA E TECNOLOGIA DO RIO GRANDE DO NORTE',
)


@dataclass(frozen=True)
class Leiaute:
    """Tags que trazem número do processo, data de depósito e inventores num bloco ``(Cd)``."""

    numero: tuple[str, ...]
    data: tuple[str, ...]
    inventores: tuple[str, ...]


LEIAUTE_PATENTE = Leiaute(numero=('(21)', '(11)'), data=('(22)',), inventores=('(72)',))
LEIAUTE_SOFTWARE = Leiaute(numero=('(21)', '(11)', '(Np)'), data=('(22)', '(Dl)'), inventores=('(72)', '(Cr)'))
# Revistas de patentes até a 2403, que ainda traziam os softwares junto.
LEIAUTE_SOFTWARE_ANTIGO = Leiaute(numero=('(Np)',), data=('(Dl)',), inventores=('(72)', '(Cr)'))


@dataclass(frozen=True)
class Importacao:
    """Como um comando baixa, lê e grava as revistas."""

    tipo: str  # descrição da PropriedadeIntelectual
    prefixo: str  # prefixo do arquivo da revista no INPI: P<numero>.zip ou PC<numero>.zip
    leiaute: Leiaute
    baixar_sempre: bool  # baixa o zip mesmo quando a pasta da revista já existe
    ler_pelo_nome_do_zip: bool  # abre o TXT pelo nome que vem no zip (senão, <codigo>.<extensão>)
    reler_em_latin1: bool  # arquivo que não decodifica é relido em ISO-8859-1
    despacho_por_codigo: bool  # despacho é único por (registro, RPI, código); senão, por (registro, RPI)


@dataclass
class Bloco:
    """Campos de um bloco ``(Cd)`` da revista, como vêm no TXT."""

    codigo: str
    numero: str | None = None
    data_deposito: str | None = None
    titulo: str | None = None
    complemento: str | None = None
    titulares: str | None = None
    inventores: str | None = None


def nome_da_instituicao() -> str:
    return Configuracao.get_valor_por_chave_str('comum', 'instituicao').upper() or NOME_PADRAO_INSTITUICAO


def pasta_da_revista(codigo_rpi: str) -> str:
    return os.path.join(settings.TEMP_DIR, f'revistas_rpi/{codigo_rpi}')


def baixar_revista(importacao: Importacao, url: str, pasta: str) -> None:
    """Baixa e descompacta o zip da revista em ``pasta``."""
    if importacao.baixar_sempre:
        arquivo_zip = zipfile.ZipFile(BytesIO(requests.get(url, timeout=settings.REQUESTS_TIMEOUT).content))
        if not os.path.exists(pasta):
            os.makedirs(pasta)
        arquivo_zip.extractall(pasta)
    elif not os.path.exists(pasta):
        os.makedirs(pasta)
        zipfile.ZipFile(BytesIO(requests.get(url, timeout=settings.REQUESTS_TIMEOUT).content)).extractall(pasta)


def ler_revista(importacao: Importacao, pasta: str, codigo_rpi: str) -> list[str]:
    """Linhas do TXT da revista descompactado em ``pasta``."""
    if any(arquivo.endswith('.txt') for arquivo in os.listdir(pasta)):
        arquivo, extensao = next(Path(pasta).glob('*.txt')), 'txt'
    else:
        arquivo, extensao = next(Path(pasta).glob('*.TXT')), 'TXT'
    caminho = f'{pasta}/{arquivo.name if importacao.ler_pelo_nome_do_zip else f"{codigo_rpi}.{extensao}"}'
    with open(caminho) as txt:
        if not importacao.reler_em_latin1:
            return txt.readlines()
        try:
            return txt.readlines()
        except Exception:
            pass
    with open(caminho, encoding='ISO-8859-1') as txt:
        return txt.readlines()


def _ler_linha(bloco: Bloco, linha: str, leiaute: Leiaute) -> None:
    tag = linha[:4]
    if tag == '(54)':
        bloco.titulo = linha[5:-1]
    elif tag in leiaute.numero:
        numero = linha[5:-3] if len(linha) > 25 else linha[5:-1]
        bloco.numero = numero.replace(' ', '').replace('-', '')
    elif tag in leiaute.data:
        bloco.data_deposito = linha.split(' ')[1][:-1]
    elif tag in ('(71)', '(73)'):
        bloco.titulares = linha
    elif tag in ('(co)', '(Co)'):
        bloco.complemento = linha[5:-1]
    elif tag in leiaute.inventores:
        bloco.inventores = linha[5:-1]


def blocos(registros: list[str], leiaute: Leiaute) -> Iterator[Bloco]:
    """Blocos ``(Cd)`` da revista, um a um (o chamador grava cada bloco antes do próximo ser lido)."""
    bloco = None
    for linha in registros:
        if linha[:4] == '(Cd)':
            if bloco is not None:
                yield bloco
            bloco = Bloco(codigo=linha.split(' ')[1][:-1])
        elif bloco is not None:
            _ler_linha(bloco, linha, leiaute)
    if bloco is not None:
        yield bloco


def data_da_revista(registros: list[str]) -> str:
    return registros[0].split(' ')[3][:-1]


def eh_da_instituicao(bloco: Bloco, nome_instituicao: str) -> bool:
    titulares = bloco.titulares
    return bool(bloco.numero and titulares and any(nome in titulares for nome in (nome_instituicao, *GRAFIAS_INSTITUICAO)))


def _atualizar_registro(registro: RegistroPropriedadeIntelectual, bloco: Bloco) -> None:
    if bloco.titulo:
        registro.titulo = bloco.titulo
    if bloco.titulares:
        registro.titulares = bloco.titulares[5:-1]
    if bloco.inventores:
        registro.inventores = bloco.inventores
    registro.save()


def _salvar_despacho(
    importacao: Importacao, registro: RegistroPropriedadeIntelectual, numero_rpi: int | str, data_rpi: str, bloco: Bloco, lida: bool
) -> None:
    chave = {'propriedadeintelectual': registro, 'rpi': numero_rpi}
    if importacao.despacho_por_codigo:
        chave['codigo'] = bloco.codigo
    if PublicacaoPropriedadeIntelectual.objects.filter(**chave).exists():
        return
    despacho = PublicacaoPropriedadeIntelectual(
        propriedadeintelectual=registro, rpi=numero_rpi, data=datetime.strptime(data_rpi, '%d/%m/%Y').date(), codigo=bloco.codigo
    )
    if bloco.complemento:
        despacho.complemento = bloco.complemento
    if lida:
        despacho.lida = True
    despacho.save()


def _registro_da_instituicao(bloco: Bloco, tipo: PropriedadeIntelectual, numero_rpi: int | str) -> RegistroPropriedadeIntelectual:
    if RegistroPropriedadeIntelectual.objects.filter(numero_processo=bloco.numero).exists():
        registro = RegistroPropriedadeIntelectual.objects.filter(numero_processo=bloco.numero).last()
    else:
        registro = RegistroPropriedadeIntelectual(numero_processo=bloco.numero, tipo=tipo, primeira_rpi=numero_rpi)
        registro.save()
    if bloco.data_deposito and not registro.data:
        registro.data = datetime.strptime(bloco.data_deposito, '%d/%m/%Y').date()
    return registro


def importar_da_instituicao(
    importacao: Importacao, registros: list[str], numero_rpi: int | str, tipo: PropriedadeIntelectual, nome_instituicao: str, lida: bool
) -> None:
    """Grava os processos da revista que têm a instituição como titular, com o despacho da revista."""
    data_rpi = data_da_revista(registros)
    for bloco in blocos(registros, importacao.leiaute):
        if eh_da_instituicao(bloco, nome_instituicao):
            registro = _registro_da_instituicao(bloco, tipo, numero_rpi)
            _atualizar_registro(registro, bloco)
            _salvar_despacho(importacao, registro, numero_rpi, data_rpi, bloco, lida)


def importar_retroativos(importacao: Importacao, registros: list[str], numero_rpi: int, todos_registros: dict[str, int]) -> None:
    """Grava os despachos de processos já cadastrados publicados antes de a instituição virar titular."""
    data_rpi = data_da_revista(registros)
    for bloco in blocos(registros, replace(importacao.leiaute, data=())):
        if bloco.numero in todos_registros:
            registro = RegistroPropriedadeIntelectual.objects.get(id=todos_registros[bloco.numero])
            _atualizar_registro(registro, bloco)
            _salvar_despacho(importacao, registro, numero_rpi, data_rpi, bloco, lida=True)


def _url_da_ultima_revista(coluna: int) -> str | None:
    navegador = mechanicalsoup.StatefulBrowser()
    try:
        navegador.open(URL_REVISTAS, timeout=100, verify=False)
    except Exception:
        return None
    try:
        return navegador.get_current_page().find('tr', class_='warning').find_all('td')[coluna].find_all('a', href=True)[1]['href']
    except Exception:
        return None


def importar_revista_recente(importacao: Importacao, numero_da_rpi: int | str | None, coluna: int) -> int | str | None:
    """Importa a revista ``numero_da_rpi`` ou, sem ela, a última publicada (coluna ``coluna`` da página do INPI).

    Sem ``numero_da_rpi``, só importa se a última revista ainda não foi importada, e a registra como a última.
    Devolve o número da revista, ou ``None`` se a página do INPI não respondeu.
    """
    nome_instituicao = nome_da_instituicao()
    tipo = PropriedadeIntelectual.objects.get(descricao=importacao.tipo)
    if numero_da_rpi:
        url_revista = f'http://revistas.inpi.gov.br/txt/{importacao.prefixo}{numero_da_rpi}.zip'
        codigo_rpi = f'{importacao.prefixo}{numero_da_rpi}'
        numero_rpi = numero_da_rpi
    else:
        url_revista = _url_da_ultima_revista(coluna)
        if url_revista is None:
            return None
        codigo_rpi = url_revista.split('/')[4].split('.')[0]
        numero_rpi = codigo_rpi[len(importacao.prefixo) :]  # P2700 ou PC2700 -> 2700
    if not tipo.ultima_rpi or tipo.ultima_rpi != numero_rpi or numero_da_rpi:
        pasta = pasta_da_revista(codigo_rpi)
        baixar_revista(importacao, url_revista, pasta)
        registros = ler_revista(importacao, pasta, codigo_rpi)
        importar_da_instituicao(importacao, registros, numero_rpi, tipo, nome_instituicao, lida=False)
        if not numero_da_rpi:
            tipo.ultima_rpi = numero_rpi
            tipo.save()
    return numero_rpi


def importar_historico(importacao: Importacao, inicio: int, fim: int, criar_pasta_na_releitura: bool = False) -> None:
    """Importa as revistas de ``inicio`` a ``fim`` e depois relê todas atrás de despachos retroativos.

    Às vezes a instituição só entra como titular depois: a primeira passada grava apenas os processos
    em que ela já é titular; a segunda, os despachos anteriores desses processos.
    """
    nome_instituicao = nome_da_instituicao()
    tipo = PropriedadeIntelectual.objects.get(descricao=importacao.tipo)
    for numero_rpi in range(inicio, fim + 1):
        codigo_rpi = f'{importacao.prefixo}{numero_rpi}'
        pasta = pasta_da_revista(codigo_rpi)
        baixar_revista(importacao, f'http://revistas.inpi.gov.br/txt/{codigo_rpi}.zip', pasta)
        importar_da_instituicao(importacao, ler_revista(importacao, pasta, codigo_rpi), numero_rpi, tipo, nome_instituicao, lida=True)
        tipo.ultima_rpi = numero_rpi
        tipo.save()

    todos_registros = dict(RegistroPropriedadeIntelectual.objects.all().values_list('numero_processo', 'id'))
    for numero_rpi in range(inicio, fim + 1):
        codigo_rpi = f'{importacao.prefixo}{numero_rpi}'
        pasta = pasta_da_revista(codigo_rpi)
        if criar_pasta_na_releitura and not os.path.exists(pasta):
            os.makedirs(pasta)
        importar_retroativos(importacao, ler_revista(importacao, pasta, codigo_rpi), numero_rpi, todos_registros)
        tipo.ultima_rpi = numero_rpi
        tipo.save()
