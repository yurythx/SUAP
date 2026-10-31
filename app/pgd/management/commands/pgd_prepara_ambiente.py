# -------------------------------------
# IMPORTAR DADOS DO QTA
# -------------------------------------

from django.core.management.base import BaseCommand

from pgd.models import PlanoTrabalhoSetorial, SolicitacaoAdesaoServidor
from rh.models import Setor


class Command(BaseCommand):
    def handle(self, *args, **options):
        setor = Setor.objects.suap_ativos().get(id=739)
        PlanoTrabalhoSetorial.objects.filter(setor=setor).delete()
        SolicitacaoAdesaoServidor.objects.filter(servidor__setor=setor).delete()
