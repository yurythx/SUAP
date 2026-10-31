from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[demandas_externas] Notifica Demandas com Pendências',
        'notifica_demandas_com_pendencias',
        crontab={'hour': 5, 'minute': 7},
    )
