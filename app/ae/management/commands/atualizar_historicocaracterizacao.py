import tqdm

from ae.models import Caracterizacao
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        for caracterizacao in tqdm.tqdm(Caracterizacao.objects.all()):
            if caracterizacao.historico_caracterizacao:
                caracterizacao.historico_caracterizacao.caracterizacao_relacionada = caracterizacao
                caracterizacao.historico_caracterizacao.save()
