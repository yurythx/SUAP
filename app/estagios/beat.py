from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[estagios] Estagios: Atualizações e Notificações',
        'estagios_atualizacoes_notificacoes',
        crontab={'hour': 0, 'minute': 9},
    )

    carregar_call_command(
        '[estagios] Estagios: Notificar Paes a Vencer',
        'estagios_notificar_paes_a_vencer',
        crontab={'hour': 1, 'minute': 9},
    )
