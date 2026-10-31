"""
Comando de management para recalcular os flags desnormalizados de todos os eventos.

Uso:
    python manage.py recalcular_flags_eventos
    python manage.py recalcular_flags_eventos --evento-id 123
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from tqdm import tqdm

from eventos.models import Evento


class Command(BaseCommand):
    help = 'Recalcula os flags desnormalizados de configuração de todos os eventos'

    def add_arguments(self, parser):
        parser.add_argument(
            '--evento-id',
            type=int,
            help='ID de um evento específico para recalcular (opcional)',
        )

    def handle(self, *args, **options):
        evento_id = options.get('evento_id')

        if evento_id:
            eventos = Evento.objects.filter(pk=evento_id)
            if not eventos.exists():
                self.stdout.write(self.style.ERROR(f'Evento #{evento_id} não encontrado'))
                return
        else:
            eventos = Evento.objects.all()

        total = eventos.count()
        alterados = 0
        erros = 0

        for evento in tqdm(eventos, desc='Recalculando flags', total=total, unit='evento'):
            try:
                old_values = (
                    evento.possui_modalidades,
                    evento.possui_configuracao_criterios_completa,
                    evento.possui_tipo_avaliador,
                )

                with transaction.atomic():
                    evento.recalcular_flags_configuracao()
                    evento.refresh_from_db()

                new_values = (
                    evento.possui_modalidades,
                    evento.possui_configuracao_criterios_completa,
                    evento.possui_tipo_avaliador,
                )

                if old_values != new_values:
                    alterados += 1

            except Exception:
                erros += 1

        self.stdout.write(f'\nTotal: {total} | Alterados: {alterados} | Erros: {erros}')
        self.stdout.write(self.style.SUCCESS('Concluído'))
