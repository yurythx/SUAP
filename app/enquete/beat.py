from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[enquete] Finalizar eventos',
        'finalizar_eventos',
        crontab={'hour': 4, 'minute': 7},
    )
    carregar_call_command(
        '[enquete] Processar Avaliações',
        'eventos_processar_avaliacoes',
        crontab={'hour': 4, 'minute': 37},
    )
