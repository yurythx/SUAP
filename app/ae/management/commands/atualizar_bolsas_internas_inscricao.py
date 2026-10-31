from ae.models import InscricaoTrabalho
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        for inscricao in InscricaoTrabalho.objects.exclude(bolsas=None):
            inscricao.bolsas_internas_externas.set(inscricao.bolsas.all())
