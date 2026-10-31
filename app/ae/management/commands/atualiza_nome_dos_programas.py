from ae.models import Programa
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        for programa in Programa.objects.all():
            nome_programa = [item for item in Programa.TIPO_CHOICES if item[0] == programa.tipo]
            if nome_programa:
                texto = f'{nome_programa[0][1]} ({programa.instituicao})'
                programa.titulo = texto
                programa.save()
