from beat.models import Intervalo
from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[protocolo] Importar Processos do SEI',
        'importar_sei',
        args=['--continuar'],
        interval=[15, Intervalo.MINUTES],
    )
