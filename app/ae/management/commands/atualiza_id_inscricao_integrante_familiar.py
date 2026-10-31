from ae.models import IntegranteFamiliarCaracterizacao
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        for registro in IntegranteFamiliarCaracterizacao.objects.filter(inscricao_caracterizacao__isnull=False):
            registro.id_inscricao = registro.inscricao_caracterizacao.id
            registro.save()
