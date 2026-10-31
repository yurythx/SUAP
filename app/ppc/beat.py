from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[ppc] Sincronizar',
        'ppc_sincronizar',
        crontab={'hour': 3, 'minute': 37},
    )
