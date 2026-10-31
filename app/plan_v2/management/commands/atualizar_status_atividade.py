"""
Comando que atualiza a o status de atividades
"""

from djtools.management.commands import BaseCommandPlus
from plan_v2.models import Acao, Atividade


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        for atividade in Atividade.objects.all():
            atividades_em_analise = 0
            if atividade.acao_pa_vinculadora:
                if (
                    atividade.validacao == Acao.SITUACAO_DEFERIDA
                    and (atividade.validacao_vinculadora == Acao.SITUACAO_ANALISADA or atividade.validacao_vinculadora == Acao.SITUACAO_NAO_ANALISADA)
                    or atividade.validacao_vinculadora == Acao.SITUACAO_DEFERIDA
                    and (atividade.validacao == Acao.SITUACAO_ANALISADA or atividade.validacao == Acao.SITUACAO_NAO_ANALISADA)
                ):
                    atividades_em_analise += 1
                if atividades_em_analise > 0:
                    atividade.acao_pa.validacao = Acao.SITUACAO_ANALISADA
                    atividade.acao_pa.save()
        print('\n FIM \n')
