import tqdm
from djtools.management.commands import BaseCommandPlus
from demandas.models import Tag


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        lote_tags = []
        lote_tamanho = 1000

        self.stdout.write('\nAtualizando o atributo "apps_relacionadas" de todas as Tags\n')
        for tag in tqdm.tqdm(Tag.objects.all()):
            tag.set_apps_relacionadas()
            lote_tags.append(tag)

            if len(lote_tags) == lote_tamanho:
                Tag.objects.bulk_update(lote_tags, ['apps_relacionadas'])
                lote_tags.clear()

        if lote_tags:
            Tag.objects.bulk_update(lote_tags, ['apps_relacionadas'])
            lote_tags.clear()
