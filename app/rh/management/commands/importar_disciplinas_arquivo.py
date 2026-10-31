import os

from django.conf import settings
from django.db import transaction

from djtools.management.commands import BaseCommandPlus
from edu.models import Disciplina


class Command(BaseCommandPlus):
    help = 'Inicia a importação disciplinas'

    @transaction.atomic
    def handle(self, *args, **options):
        arquivo = os.path.join(settings.BASE_DIR, 'rh/static/rh/disciplinas.txt')
        existentes = set(Disciplina.objects.values_list('descricao', flat=True))
        novos = []
        seen = set()
        with open(arquivo) as txt_file:
            for linha in txt_file:
                descricao = linha.strip()
                if not descricao or descricao in existentes or descricao in seen:
                    continue
                seen.add(descricao)
                novos.append(Disciplina(descricao=descricao))
        Disciplina.objects.bulk_create(novos, batch_size=1000)
        self.stdout.write(f'Disciplinas criadas: {len(novos)}')
