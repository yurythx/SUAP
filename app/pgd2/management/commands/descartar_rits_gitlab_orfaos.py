"""Remove RITs lançados via GitLab cujo MR foi fechado sem merge (órfãos)."""

from __future__ import annotations

import logging
from argparse import ArgumentParser
from typing import Any

from django.core.management.base import BaseCommand

from djtools.utils import gitlab
from pgd2.models import PlanoIndividualTrabalho, RelatorioIndividualTrabalho

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Remove RITs lançados via GitLab cujo MR foi fechado sem merge (órfãos em EM_CADASTRO_RIT).'

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument('--dry-run', action='store_true', help='Apenas lista, não remove.')

    def handle(self, *args: Any, **options: Any) -> None:
        dry_run: bool = options['dry_run']
        # Só candidatos: têm proveniência GitLab E o RIT do mês ainda está editável.
        candidatos = RelatorioIndividualTrabalho.objects.filter(
            gitlab_mr_iid__isnull=False,
            entrega_pit__pit__situacao_rit=PlanoIndividualTrabalho.EM_CADASTRO_RIT,
        ).select_related('entrega_pit__pit')

        removidos = 0
        for rit in candidatos:
            try:
                mr = gitlab.get_merge_request(rit.gitlab_project_id, rit.gitlab_mr_iid)
            except Exception as erro:
                logger.warning(
                    'Erro ao consultar MR %s!%s ao descartar RITs órfãos; pulando.', rit.gitlab_project_id, rit.gitlab_mr_iid, exc_info=erro
                )
                self.stderr.write(f'MR {rit.gitlab_project_id}!{rit.gitlab_mr_iid}: erro ao consultar ({erro}); pulando.')
                continue

            # 'closed' = fechado sem merge; MR mergeado tem state 'merged' e aberto 'opened'.
            if mr.get('state') == 'closed':
                pit = rit.entrega_pit.pit
                self.stdout.write(f'Removendo RIT {rit.id} (MR {rit.gitlab_project_id}!{rit.gitlab_mr_iid} fechado sem merge).')
                if not dry_run:
                    rit.delete()
                    pit.calcular_pit()
                removidos += 1

        prefixo = '(dry-run) ' if dry_run else ''
        self.stdout.write(self.style.SUCCESS(f'{prefixo}{removidos} RIT(s) órfão(s) processado(s).'))
