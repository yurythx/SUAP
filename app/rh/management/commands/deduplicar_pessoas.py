from __future__ import annotations

from argparse import ArgumentParser, ArgumentTypeError
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from django.conf import settings

from djtools.management.commands import BaseCommandPlus


def _inteiro_positivo(texto: str) -> int:
    try:
        valor = int(texto)
    except ValueError:
        valor = 0
    if valor < 1:
        raise ArgumentTypeError(f'{texto!r} não é um inteiro maior ou igual a 1')
    return valor


@contextmanager
def _sem_historico() -> Iterator[None]:
    """Desliga o ``djtools.history`` só neste processo, durante o comando.

    A auditoria da deduplicação é a ``DeduplicacaoPessoa``. Com o histórico ligado, cada perdedora apagada (``pre_delete``) e cada
    sobrevivente gravada (``QuerySet.update``) emitiriam um registro com o ``str`` de cada FK: centenas de milhares de registros e
    minutos de janela a mais, repetindo o que a auditoria já guarda.
    """
    anterior = settings.USE_HISTORY
    settings.USE_HISTORY = False
    try:
        yield
    finally:
        settings.USE_HISTORY = anterior


class Command(BaseCommandPlus):
    help = 'Deduplica PessoaFisica por documento (CPF/passaporte): planejar → relatorio → aplicar. Ver docs/operacoes/deduplicar-pessoas.md.'

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument('etapa', choices=['planejar', 'relatorio', 'aplicar'])
        parser.add_argument('--csv', type=Path, help='relatorio: grava as linhas do plano/auditoria neste CSV (contém CPF).')
        parser.add_argument('--lote', type=_inteiro_positivo, default=1000, help='aplicar: grupos por transação.')

    def handle(self, *args: Any, etapa: str, csv: Path | None = None, lote: int = 1000, **options: Any) -> None:
        with _sem_historico():
            self._executar(etapa, csv, lote)

    def _executar(self, etapa: str, csv: Path | None, lote: int) -> None:
        # Sem transaction.atomic aqui: aplicar() abre uma transação por lote e grava o ERRO fora da transação desfeita.
        from rh.deduplicacao import relatorio
        from rh.deduplicacao.aplicacao import aplicar
        from rh.deduplicacao.plano import planejar

        if etapa == 'planejar':
            totais = planejar()
        elif etapa == 'aplicar':
            totais = aplicar(lote=lote)
        else:
            totais = relatorio.resumo()
            if csv:
                self.stdout.write(f'Atenção: {csv} contém CPF (dado pessoal).')
                totais['linhas no CSV'] = relatorio.exportar_csv(csv)
        for chave, total in sorted(totais.items()):
            self.stdout.write(f'{chave}: {total}')
        if etapa == 'relatorio':
            self._imprimir_trava()

    def _imprimir_trava(self) -> None:
        """Os contadores da trava da migration rh/0111 (4.0.0): o portão do runbook antes de instalá-la."""
        from django.db import connection

        from rh.deduplicacao.verificacao import pendencias

        with connection.cursor() as cursor:
            totais = pendencias(cursor)
        for chave, total in totais.items():
            self.stdout.write(f'trava da 4.0.0 — {chave}: {total}')
        self.stdout.write(f'trava da 4.0.0: {"bloqueada" if any(totais.values()) else "liberada"}')
