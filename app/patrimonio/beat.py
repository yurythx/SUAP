from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[patrimonio] Depreciar inventários',
        'patrimonio_depreciar_inventarios',
        crontab={'hour': 3, 'minute': 14},
    )
