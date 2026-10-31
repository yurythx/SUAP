from comum.models import Vinculo
from djtools.management.commands import BaseCommandPlus
from edu.models import Aluno


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        # foto migrou de PessoaFisica para Vinculo; Aluno.foto continua campo próprio.
        Vinculo.objects.update(foto=None)
        Aluno.objects.update(foto='')
