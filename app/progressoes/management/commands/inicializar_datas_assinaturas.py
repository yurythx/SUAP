from djtools.management.commands import BaseCommandPlus
from progressoes.models import ProcessoProgressaoAvaliacao

"""
    Avaliações que possuem assinaturas sem data
"""


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        print('Inicializando datas das assinaturas ...')
        avaliacoes = ProcessoProgressaoAvaliacao.objects.all()
        for avaliacao in avaliacoes:
            if avaliacao.data_avaliacao:
                if avaliacao.assinatura_avaliador and not avaliacao.data_assinatura_avaliador:
                    avaliacao.data_assinatura_avaliador = avaliacao.data_avaliacao
                if avaliacao.assinatura_avaliado and not avaliacao.data_assinatura_avaliado:
                    avaliacao.data_assinatura_avaliador = avaliacao.data_avaliacao
                if avaliacao.assinatura_chefe_imediato and not avaliacao.data_assinatura_chefe_imediato:
                    avaliacao.data_assinatura_chefe_imediato = avaliacao.data_assinatura_chefe_imediato
                #
                avaliacao.save()
                print(avaliacao)
