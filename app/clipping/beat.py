from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[clipping] Importar Notícias',
        'clipping_importar',
        crontab={'minute': 0, 'hour': 10},
    )
