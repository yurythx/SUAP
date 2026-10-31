import tqdm

from djtools.management.commands import BaseCommandPlus
from siads.models import GrupoMaterialPermanente, MaterialPermanente


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        print('Corrigindo materiais')
        for material in tqdm.tqdm(MaterialPermanente.objects.all()):
            material.uo = material.entrada.entrada.uo
            material.save()
        print('Corrigindo grupos')
        for grupo in tqdm.tqdm(GrupoMaterialPermanente.objects.filter(uo__isnull=True)):
            material = MaterialPermanente.objects.filter(grupo=grupo)
            if material.exists():
                material = material.first()
                grupo.uo = material.uo
                grupo.save()

        print('Fim da operção')
