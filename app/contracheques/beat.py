from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[contracheques] Importar',
        'importar_contracheques',
        crontab={'hour': 1, 'minute': 7},
    )
