from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[integracao_wifi] Revogar Autorizações de Dispositivos',
        'revogar_autorizacoes_dispositivos',
        crontab={'hour': 4, 'minute': 7},
    )
