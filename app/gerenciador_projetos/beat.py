from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[gerenciador_projetos] Tarefas Recorrentes',
        'gp_tarefas_recorrentes',
        crontab={'hour': 1, 'minute': 7},
    )
