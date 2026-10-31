from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[eleicao] Atualizar público de eleições em andamento',
        'atualizar_publico_eleicoes_em_andamento',
        crontab={'hour': 4, 'minute': 7},
    )
