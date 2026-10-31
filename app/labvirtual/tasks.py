import datetime

from djtools.utils import print_
from suap import celery_app


def get_sync_task_name():
    return '[labvirtual] Sincronizar Laboratórios VDI'


@celery_app.task(bind=True)
def sync_labs_vdi(self):
    from djtools.utils import get_datetime_now
    from labvirtual.models import AgendamentoLabVirtual

    now = get_datetime_now()
    #
    print_('[Celery-SUAP] Verificando agendamentos............')
    inativos = AgendamentoLabVirtual.objects.inativos().filter(data_hora_inicio__lte=now, data_hora_fim__gte=now)
    for agendamento in inativos:
        print_(f'[Celery-SUAP] Ativar Agendamento Request: {self.request!r}')
        agendamento.ativar()
        agendamento.save()
    #
    ativos = AgendamentoLabVirtual.objects.ativos().filter(data_hora_fim__lte=now)
    for agendamento in ativos:
        print_(f'[Celery-SUAP] Desativando Agendamento Request: {self.request!r}')
        agendamento.inativar()
        agendamento.save()

    #
    agendamentos = AgendamentoLabVirtual.objects.ativos().filter(data_hora_fim__lte=now + datetime.timedelta(minutes=5))
    for agendamento in agendamentos:
        print_(f'[Celery-SUAP] Enviando notificação de expiração: {self.request!r}')
        eta = agendamento.data_hora_fim - now
        msg = f'A sua sessão vai expirar em {eta} minutos. Salve o seu trabalho.'
        agendamento.enviar_notificacao(msg)


def finalizar_agendamentos_vdi():
    from labvirtual.models import SolicitacaoLabVirtual

    solicitacoes = SolicitacaoLabVirtual.objects.expiradas()
    for solicitacao in solicitacoes:
        solicitacao.finalizar()
        solicitacao.save()
