from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[pafc] Sincronizar',
        'pafc_sincronizar',
        crontab={'hour': 4, 'minute': 7},
    )
    carregar_call_command(
        '[pafc] Notificar Pendências de Revisão Técnica',
        'pafc_notificar_pendencia_revisao_tecnica',
        crontab={'hour': 4, 'minute': 37},
    )
