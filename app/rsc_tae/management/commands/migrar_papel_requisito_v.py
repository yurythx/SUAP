"""
Management command: migrar_papel_requisito_v

Funde os 8 itens do Requisito V (4 do decreto desdobrados em titular/substituto) em 4 itens
canônicos, tornando titular/substituto o atributo ``papel`` de cada comprovante.

A lógica é compartilhada com a data migration que roda no deploy (``rsc_tae.fusao_requisito_v``):
este command é para uso manual / verificação (dry-run por padrão). Idempotente.

Uso:
    python manage.py migrar_papel_requisito_v            # simulação (relatório, não grava)
    python manage.py migrar_papel_requisito_v --commit   # aplica a fusão
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from rsc_tae.fusao_requisito_v import fundir_requisito_v
from rsc_tae.models import RolSaberCompetencia, RolSaberCompetenciaAnexo, RolSaberCompetenciaPreenchimento


class Command(BaseCommand):
    help = 'Funde os 8 itens do Requisito V em 4 canônicos (titular/substituto vira o papel do comprovante).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--commit',
            action='store_true',
            help='Aplica a fusão. Sem esta flag, o comando apenas simula (rollback ao final).',
        )

    def handle(self, *args, **options):
        pares = None
        try:
            with transaction.atomic():
                pares = fundir_requisito_v(
                    RolSaberCompetencia, RolSaberCompetenciaAnexo, RolSaberCompetenciaPreenchimento, escrever=self.stdout.write
                )
                if pares and not options['commit']:
                    raise _Rollback
        except _Rollback:
            self.stdout.write(self.style.WARNING('\nSIMULAÇÃO — nenhuma alteração foi gravada. Rode com --commit para aplicar.'))
            return

        if not pares:
            self.stdout.write(self.style.WARNING('Nenhum par titular/substituto ativo encontrado no Requisito V (já migrado?).'))
            return
        self.stdout.write(self.style.SUCCESS(f'\n{len(pares)} par(es) fundido(s). Requisito V agora tem {len(pares)} itens canônicos.'))


class _Rollback(Exception):
    """Sentinela para forçar rollback da transação em modo simulação."""
