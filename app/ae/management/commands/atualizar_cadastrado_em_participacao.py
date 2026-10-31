import tqdm

from ae.models import Participacao
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        for part in tqdm.tqdm(Participacao.objects.exclude(atualizado_em=None)):
            part.cadastrado_em = part.atualizado_em
            part.cadastrado_por = part.atualizado_por.user
            part.save()
