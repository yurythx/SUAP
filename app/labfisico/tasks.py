from djtools.utils import print_
from suap import celery_app


def get_sync_task_name():
    return '[labfisico] Syncronizar Laboratórios Guacamole'


@celery_app.task(bind=True)
def sync_labs_guacamole(self):
    from djtools.utils import get_datetime_now
    from labfisico.models import AgendamentoLabFisico

    agora = get_datetime_now()

    inativos = AgendamentoLabFisico.objects.inativos().filter(data_hora_inicio__lte=agora, data_hora_fim__gte=agora)
    for agendamento in inativos:
        print_(f'[Celery-SUAP] Ativando agendamentos dos laboratórios físicos. Request: {self.request!r}')
        agendamento.ativar()
        agendamento.save()

    ativos = AgendamentoLabFisico.objects.ativos().filter(data_hora_fim__lte=agora)
    for agendamento in ativos:
        print_(f'[Celery-SUAP] Encerrrando agendamentos dos laboratórios físicos. Request: {self.request!r}')
        agendamento.inativar()
        agendamento.save()


def finalizar_agendamentos_guacamole():
    from labfisico.models import SolicitacaoLabFisico

    solicitacoes = SolicitacaoLabFisico.objects.expiradas()
    for solicitacao in solicitacoes:
        solicitacao.finalizar()
        solicitacao.save()
