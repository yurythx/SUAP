from beat.models import Intervalo
from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[saude] Atualiza Validade dos Passaportes Vacinais',
        'atualiza_validade_passaportes_vacinais',
        interval=[1, Intervalo.HOURS],
    )
    carregar_call_command(
        '[saude] Notificar Passaportes Inválidos',
        'notificar_passaportes_invalidos',
        crontab={'minute': 15, 'hour': 22},
    )
    carregar_call_command(
        '[saude] Encerrar Avaliações Biomédicas Inativas',
        'encerra_avaliacoes_biomedicas_inativas',
        crontab={'minute': 30, 'hour': 22},
    )
