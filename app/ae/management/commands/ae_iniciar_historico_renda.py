from ae.models import Caracterizacao, HistoricoRendaFamiliar
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        for c in Caracterizacao.objects.all().order_by('id'):
            c.save()
        print((Caracterizacao.objects.count(), HistoricoRendaFamiliar.objects.count()))
