from tqdm import tqdm

from djtools.management.commands import BaseCommandPlus
from rh.models import Setor


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        for setor in tqdm(Setor.objects.siape().all()):
            chefes = setor.chefes
            print(f'{setor.sigla} - {chefes}')
