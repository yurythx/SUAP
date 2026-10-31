from beat.models import Intervalo
from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[centralservicos] Verifica SLA Estourado',
        'centralservicos_verifica_sla_estourado',
        interval=[1, Intervalo.HOURS],
    )
    carregar_call_command(
        '[centralservicos] Notificações Diárias',
        'centralservicos_notificacoes_diarias',
        crontab={'hour': 4, 'minute': 7},
    )
