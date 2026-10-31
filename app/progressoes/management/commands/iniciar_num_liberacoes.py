from djtools.management.commands import BaseCommandPlus
from progressoes.models import ProcessoProgressao, ProcessoProgressaoAvaliacao

"""
    Avaliações em Processos Finalizados ou Em Trâmite
        Se número de liberação = 0, número de liberação = 1
"""


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        print('Inicializando número de liberações das avaliações de progressões TAE ...')
        avaliacoes = ProcessoProgressaoAvaliacao.objects.all().exclude(periodo__processo_progressao__status=ProcessoProgressao.STATUS_A_INICIAR)
        for avaliacao in avaliacoes:
            if avaliacao.numero_liberacoes == 0:
                avaliacao.numero_liberacoes = 1
                avaliacao.save()
