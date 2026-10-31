from djtools.management.commands import BaseCommandPlus
from pesquisa.models import Projeto


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        for projeto in Projeto.objects.all():
            projeto.vinculo_coordenador = projeto.get_responsavel()
            projeto.save()
