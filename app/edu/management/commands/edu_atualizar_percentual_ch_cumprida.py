import tqdm

from djtools.management.commands import BaseCommandPlus
from edu.models import Aluno


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        for a in tqdm.tqdm(Aluno.objects.filter(matriz__isnull=False)):
            a.atualizar_percentual_ch_cumprida()
