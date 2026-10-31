from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[tesouro_gerencial] Importar do Tesouro',
        'importar_do_tesouro',
        crontab={
            'hour': '7',
            'minute': '0',
        },
    )
