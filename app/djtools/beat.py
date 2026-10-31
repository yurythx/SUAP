from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[djtools] Deletar logs de emails antigos',
        'deletar_log_emails_antigos',
        crontab={'hour': 1, 'minute': 7},
    )
