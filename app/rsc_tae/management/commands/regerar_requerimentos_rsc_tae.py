"""
Management command: regerar_requerimentos_rsc_tae

Regenera o snapshot do requerimento (PDF protocolado) dos processos que já concluíram o
preenchimento, garantindo que a assinatura eletrônica (hash SHA-256) do preenchimento conste
no documento. Para processos sem hash de preenchimento, gera a assinatura antes de regerar.

Alcance: processos com ``data_entrada_requerimento`` preenchida (preenchimento concluído).

Uso:
    python manage.py regerar_requerimentos_rsc_tae            # regenera todos
    python manage.py regerar_requerimentos_rsc_tae --dry-run  # apenas lista o que faria
"""

from django.core.management.base import BaseCommand

from rsc_tae.models import ProcessoRSCTae
from rsc_tae.views.documentos import anexar_requerimento_ao_processo


class Command(BaseCommand):
    help = 'Regenera os snapshots de requerimento dos processos concluídos, incluindo a assinatura (hash) do preenchimento.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Apenas lista os processos que seriam regenerados.')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        processos = ProcessoRSCTae.objects.filter(data_entrada_requerimento__isnull=False).order_by('pk')

        total = processos.count()
        self.stdout.write(f'Processos concluídos encontrados: {total}')

        assinados, regenerados, falhas = 0, 0, 0
        for processo in processos:
            if dry_run:
                marca = 'com hash' if processo.assinatura_preenchimento_hash else 'SEM hash (será gerado)'
                self.stdout.write(f'  [dry-run] processo {processo.pk} — {marca}')
                continue

            if not processo.assinatura_preenchimento_hash:
                processo.gerar_assinatura_preenchimento()
                assinados += 1

            if anexar_requerimento_ao_processo(processo):
                regenerados += 1
            else:
                falhas += 1
                self.stdout.write(self.style.WARNING(f'  falha ao regenerar o requerimento do processo {processo.pk}'))

        if dry_run:
            self.stdout.write(self.style.SUCCESS('Dry-run concluído.'))
            return

        self.stdout.write(
            self.style.SUCCESS(f'Concluído: {regenerados} requerimento(s) regenerado(s), {assinados} assinatura(s) gerada(s), {falhas} falha(s).')
        )
