import tqdm

from djtools.management.commands import BaseCommandPlus
from projetos.models import ProjetoAnexo


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        for anexo in tqdm.tqdm(ProjetoAnexo.objects.filter(vinculo_membro_equipe__isnull=True, participacao__isnull=False)):
            anexo.vinculo_membro_equipe = anexo.participacao.vinculo_pessoa
            anexo.save()
