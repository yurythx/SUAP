from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[rsc] Checar Datas Processos',
        'checa_datas_processos_rsc',
        crontab={'hour': 2, 'minute': 7},
    )
