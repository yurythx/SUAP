from django.apps import apps
from django.conf import settings

from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    """
    Command criado para reassinar os depachos devido a um erro ao processamento
    das variáveis
    """

    def handle(self, *args, **options):
        self.gerar_numero_protocolo_fisico()

    def gerar_numero_protocolo_fisico(self):
        if 'protocolo' in settings.INSTALLED_APPS:
            Processo = apps.get_model('processo_eletronico', 'Processo')
            for processo in Processo.objects.filter(numero_protocolo_fisico__isnull=True):
                processo.save()
