from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[documento_eletronico] Remove Revisões',
        'delete_revisions_documento_eletronico',
        crontab={'hour': 4, 'minute': 7},
    )
