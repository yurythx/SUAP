from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[professor_titular] Checar prazos e reservas',
        'checar_datas',
        crontab={'hour': 2, 'minute': 7},
    )
