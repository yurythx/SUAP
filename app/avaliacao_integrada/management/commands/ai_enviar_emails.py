from avaliacao_integrada.models import Avaliacao
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, **options):
        for avaliacao in Avaliacao.objects.all():
            avaliacao.enviar_emails()
