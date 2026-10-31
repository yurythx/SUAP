from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[licenca_capacitacao] Processar Quantitativos',
        'processar_quantitativo_lic_capacitacao',
        crontab={'hour': 4, 'minute': 7},
    )
