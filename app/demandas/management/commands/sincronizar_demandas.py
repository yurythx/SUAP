from demandas.models import Demanda, Situacao
from demandas.utils import sincronizar_demandas_atualizacoes
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def add_arguments(self, parser):
        parser.add_argument('pks', nargs='*', type=int)

    def handle(self, *args, **options):
        pks = options.get('pks')
        qs = Demanda.objects.filter(situacao=Situacao.ESTADO_EM_IMPLANTACAO, id_merge_request__isnull=False)
        if pks:
            qs = qs.filter(pk__in=pks)
        for demanda in qs:
            sincronizar_demandas_atualizacoes(demanda)
