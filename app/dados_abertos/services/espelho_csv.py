"""Espelho CSV de um recurso JSON: o mesmo conteúdo, em tabela.

Um recurso JSON pode ganhar um gêmeo em CSV — mesmo dataset, mesmas colunas — para quem consome
o catálogo com planilha. O espelho é **derivado**, não uma cópia solta: guarda ``derivado_de`` e é
regravado sempre que a origem muda, inclusive pela rotina automática. Cópia única envelheceria em
silêncio, publicando dado velho ao lado do novo.

O espelho nasce sem ``url`` de propósito: ``atualizacao_service`` só coleta recurso com URL, e a
URL da origem devolve JSON — um espelho "coletável" gravaria JSON dentro de um ``.csv``.
"""

from __future__ import annotations

import csv
import io
import logging
from pathlib import Path

from django.core.files.base import ContentFile
from django.utils import timezone

from dados_abertos.enums import FormatoRecurso
from dados_abertos.models import RecursoDados
from dados_abertos.services import coleta

logger = logging.getLogger(__name__)

SUFIXO_NOME = ' (CSV)'


class EspelhoIndisponivel(ValueError):
    """O conteúdo da origem não vira tabela — não há CSV a gerar."""


def _ler(recurso: RecursoDados) -> bytes | None:
    try:
        recurso.arquivo.open('rb')
        try:
            return recurso.arquivo.read()
        finally:
            recurso.arquivo.close()
    except FileNotFoundError, OSError, ValueError:
        return None


def _tabular(origem: RecursoDados):
    """Leitura da origem, ou ``EspelhoIndisponivel`` com o motivo legível."""
    conteudo = _ler(origem)
    if conteudo is None:
        raise EspelhoIndisponivel('Arquivo da origem indisponível para leitura.')
    tabular = coleta.ler_tabular(conteudo.decode('utf-8', 'replace'), origem.formato)
    if tabular.erro:
        raise EspelhoIndisponivel(tabular.erro)
    if not tabular.colunas:
        raise EspelhoIndisponivel('O conteúdo não tem colunas para virar tabela.')
    return tabular


def _conteudo_csv(tabular) -> ContentFile:
    buffer = io.StringIO()
    escritor = csv.writer(buffer)
    escritor.writerow(tabular.colunas)
    escritor.writerows(tabular.linhas)
    return ContentFile(buffer.getvalue().encode('utf-8'))


def _nome_arquivo(origem: RecursoDados) -> str:
    return f'{Path(origem.arquivo.name or origem.nome).stem}.csv'


def _criar(origem: RecursoDados, tabular, conteudo: ContentFile) -> RecursoDados:
    """Cria o espelho pelo ``save()`` normal: recurso novo é conteúdo novo, e reabre o LAI."""
    espelho = RecursoDados(
        dataset=origem.dataset,
        derivado_de=origem,
        nome=f'{origem.nome}{SUFIXO_NOME}',
        descricao=origem.descricao,
        formato=FormatoRecurso.CSV,
        mimetype='text/csv',
        esquema=tabular.colunas,
    )
    espelho.arquivo.save(_nome_arquivo(origem), conteudo, save=False)
    espelho.save()
    return espelho


def atualizar_espelho(origem: RecursoDados, *, via_rotina: bool = False) -> RecursoDados:
    """Cria ou regrava o recurso CSV derivado de ``origem``.

    Args:
        origem: Recurso cujo conteúdo será tabulado (tipicamente JSON).
        via_rotina: ``True`` quando quem chama é a atualização automática. Nesse caso a gravação
            usa ``update()``, que não dispara ``save()`` e portanto **não reabre a análise do
            LAI** — mesma regra do original: a rotina re-coleta a mesma URL, e quem reabre quando
            o esquema muda é a origem.

    Returns:
        RecursoDados: O espelho criado ou atualizado.

    Raises:
        EspelhoIndisponivel: Quando o conteúdo da origem não vira tabela.
    """
    tabular = _tabular(origem)
    conteudo = _conteudo_csv(tabular)
    espelho = origem.derivados.first()
    if espelho is None:
        return _criar(origem, tabular, conteudo)

    espelho.arquivo.save(_nome_arquivo(origem), conteudo, save=False)
    if via_rotina:
        # `data_atualizacao` vai explícito porque `update()` não aciona o `auto_now` — e é ele que
        # o sync do CKAN compara para decidir reenviar o arquivo.
        RecursoDados.objects.filter(pk=espelho.pk).update(
            arquivo=espelho.arquivo.name,
            esquema=tabular.colunas,
            data_atualizacao=timezone.now(),
        )
        return espelho
    espelho.esquema = tabular.colunas
    espelho.save()
    return espelho


def atualizar_espelhos(origens) -> tuple[list[RecursoDados], list[str]]:
    """Regrava os espelhos já existentes das origens dadas. Origem sem espelho é ignorada.

    Returns:
        tuple: os espelhos atualizados e os avisos das origens que deixaram de virar tabela.
    """
    espelhos: list[RecursoDados] = []
    avisos: list[str] = []
    for origem in origens:
        if not origem.derivados.exists():
            continue
        try:
            espelhos.append(atualizar_espelho(origem, via_rotina=True))
        except EspelhoIndisponivel as erro:
            logger.warning('Espelho CSV do recurso %s não pôde ser regravado: %s', origem.pk, erro)
            avisos.append(f'O espelho CSV de "{origem.nome}" não foi atualizado: {erro}')
    return espelhos, avisos
