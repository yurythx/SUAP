from beat.utils import carregar_call_command


def load_tasks_schedule():

    carregar_call_command(
        '[frota] Notificar Revisões Viaturas',
        'notificar_revisoes_viaturas',
        crontab={'hour': 1, 'minute': 7, 'day_of_week': 1},
    )
