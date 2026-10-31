import logging

import tqdm
from django.db.models import Q

from djtools.management.commands import BaseCommandPlus

from progressao_docente.models import Avaliacao

logger = logging.getLogger(__name__)


class Command(BaseCommandPlus):
    help = 'Revalida assinaturas (avaliador/ciência) cuja divergência é apenas de ordenação dos itens. Não toca em divergências reais.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Apenas relata, sem gravar.')
        parser.add_argument('--avaliacao', type=int, default=None, help='ID de uma Avaliacao específica; se omitido, processa todas as assinadas.')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        contadores = {'revalidada': 0, 'divergencia': 0, 'ja_valida': 0, 'sem_assinatura': 0}
        qs = Avaliacao.objects.filter(Q(assinatura_avaliador__gt='') | Q(assinatura_avaliado_processo__gt='')).select_related('progressao')
        if options['avaliacao'] is not None:
            qs = qs.filter(pk=options['avaliacao'])
            if not qs.exists():
                self.stdout.write(self.style.WARNING(f'Avaliação {options["avaliacao"]} não encontrada ou sem assinatura. Nada a fazer.'))
                return
        # chunk_size explícito para lotes grandes; total=count() é só estimativa da barra
        # (count + iterator são duas queries — sob concorrência o total pode divergir levemente do iterado)
        # disable=None: mostra a barra quando há TTY (execução manual) e fica silencioso no deploy (data migration)
        for avaliacao in tqdm.tqdm(qs.iterator(chunk_size=500), total=qs.count(), desc='Revalidando assinaturas', disable=None):
            resultado = avaliacao.revalidar_assinaturas_se_apenas_ordenacao(dry_run=dry_run)
            for estado in resultado.values():
                contadores[estado] += 1
        logger.info('Revalidação de assinaturas (dry_run=%s): %s', dry_run, contadores)
        self.stdout.write(self.style.SUCCESS(f'Revalidação concluída (dry_run={dry_run}): {contadores}'))
