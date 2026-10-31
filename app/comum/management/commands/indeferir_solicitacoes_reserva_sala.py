from datetime import datetime

from comum.models import SolicitacaoReservaSala
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    # UC 06 - Indeferir solicitações fora de prazo
    # Todas as solicitações de reservas não avaliadas fora de prazo, isto é, data final menos que data atual, serão automaticamente indeferidas.
    def handle(self, *args, **options):
        data_avaliacao = datetime.now()
        solicitacoes_nao_avaliadas = SolicitacaoReservaSala.objects.filter(status=SolicitacaoReservaSala.STATUS_AGUARDANDO_AVALIACAO)
        solicitacoes_antigas = solicitacoes_nao_avaliadas.filter(data_fim__lt=datetime.now())
        self.indeferir_solicitacoes(solicitacoes_antigas, data_avaliacao)
        solicitacoes_futuras = solicitacoes_nao_avaliadas.exclude(data_fim__lt=datetime.now()).exclude(
            recorrencia=SolicitacaoReservaSala.RECORRENCIA_EVENTO_UNICO
        )
        self.indeferir_solicitacoes_recorrentes(solicitacoes_futuras, data_avaliacao)

    def indeferir_solicitacoes(self, solicitacoes, data_avaliacao):
        for solicitacao in solicitacoes:
            # agendamento não foi avaliado com antecedência
            solicitacao.data_avaliacao = data_avaliacao
            solicitacao.status = SolicitacaoReservaSala.STATUS_INDEFERIDA
            solicitacao.observacao_avaliador = 'A solicitação não foi avaliado por perda do prazo.'
            # atualiza o agendamento
            solicitacao.save()
            # email para solicitante e avalidores da sala
            solicitacao.notificar_avaliacao()

    def indeferir_solicitacoes_recorrentes(self, solicitacoes, data_avaliacao):
        for solicitacao in solicitacoes:
            datas = solicitacao.get_datas_solicitadas()
            if datas:
                # pegando a ultima da final
                data_fim = datas[-1][-1]

            if not datas or data_fim < data_avaliacao:
                # agendamento não foi avaliado com antecedência
                solicitacao.data_avaliacao = data_avaliacao
                solicitacao.status = SolicitacaoReservaSala.STATUS_INDEFERIDA
                solicitacao.observacao_avaliador = 'A solicitação não foi avaliado por perda do prazo.'
                # atualiza o agendamento
                solicitacao.save()
                # email para solicitante e avalidores da sala
                solicitacao.notificar_avaliacao()
