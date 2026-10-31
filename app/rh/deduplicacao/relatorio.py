"""Relatório do plano/auditoria da deduplicação. O CSV contém CPF: é dado pessoal (LGPD)."""

from __future__ import annotations

import csv
import os
from pathlib import Path

from django.conf import settings
from django.core.management import CommandError
from django.db import transaction
from django.db.models import Count, Q

from rh.models import DeduplicacaoPessoa

COLUNAS = ['id', 'pf_id', 'sobrevivente_id', 'documento', 'acao', 'campo', 'valor_original', 'motivo', 'criado_em', 'aplicado_em']


def resumo() -> dict[str, int]:
    """Total de linhas do plano/auditoria por ação, separando pendentes de aplicadas."""
    linhas = DeduplicacaoPessoa.objects.annotate(pendente=Q(aplicado_em__isnull=True)).values('acao', 'pendente').annotate(total=Count('id'))
    return {f'{linha["acao"]} ({"pendente" if linha["pendente"] else "aplicada"})': linha['total'] for linha in linhas}


def exportar_csv(caminho: Path) -> int:
    """Grava o plano/auditoria em ``caminho`` (fora do MEDIA_ROOT) e devolve o número de linhas."""
    if caminho.resolve().is_relative_to(Path(settings.MEDIA_ROOT).resolve()):
        raise CommandError('O CSV tem CPF (dado pessoal): grave fora do MEDIA_ROOT.')
    total = 0
    # 0600: só o dono lê. O chmod estreita também um arquivo que já existia com outra permissão.
    descritor = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.chmod(caminho, 0o600)
    with os.fdopen(descritor, 'w', newline='', encoding='utf-8') as arquivo:
        escritor = csv.writer(arquivo)
        escritor.writerow(COLUNAS)
        # atomic: cursor de servidor só é seguro atrás do pgbouncer (modo transaction) dentro de uma transação (ver planejar)
        with transaction.atomic():
            for linha in DeduplicacaoPessoa.objects.order_by('pk').values_list(*COLUNAS).iterator(chunk_size=5000):
                escritor.writerow(linha)
                total += 1
    return total
