from beat.models import Intervalo
from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[conectagov_pen] Processar Pendências do Barramento', 'processar_pendencias_barramento', interval=[5, Intervalo.MINUTES], expire_seconds=300
    )
