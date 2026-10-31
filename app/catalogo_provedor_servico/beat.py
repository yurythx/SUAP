from beat.models import Intervalo
from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[catalogo_provedor_servico] Enviar e-mail de avaliação de serviços',
        'enviar_email_avaliacao_de_servicos',
        kwargs={
            'timeout': 1200,
        },
        interval=[1, Intervalo.HOURS],
        expire_seconds=3000,
    )
    carregar_call_command(
        '[catalogo_provedor_servico] Enviar notificações pelo notifica.gov.br',
        'enviar_notificacoes_notifica_govbr',
        interval=[3, Intervalo.HOURS],
        expire_seconds=9000,
    )
    carregar_call_command(
        '[catalogo_provedor_servico] Expirar solicitações incompletas',
        'expirar_solicitacoes_incompletas',
        crontab={'hour': 4, 'minute': 30},
    )
