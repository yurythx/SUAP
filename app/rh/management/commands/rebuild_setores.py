from django.core.management.base import BaseCommand
from rh.models import Setor


class Command(BaseCommand):
    help = 'Reconstrói a árvore MPTT do modelo Setor'

    def handle(self, *args, **kwargs):
        Setor.arvore.rebuild()
        self.stdout.write(self.style.SUCCESS('Árvore MPTT de Setor reconstruída com sucesso.'))
