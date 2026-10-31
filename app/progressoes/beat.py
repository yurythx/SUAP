from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[progressoes] Servidores a Progredir',
        'servidores_a_progredir',
        args=['-s'],
        crontab={'hour': 2, 'minute': 7},
    )
    carregar_call_command(
        '[progressoes] Alertar Responsáveis por Processos',
        'alertar_responsaveis_processos',
        crontab={'hour': 2, 'minute': 37},
    )
