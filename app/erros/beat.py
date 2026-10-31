from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[erros] Popular Links do Gitlab',
        'popular_links_gitlab',
        crontab={'hour': 3, 'minute': 7},
    )
