from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[compras] Atualizar Etapa Atual',
        'compras_atualizar_etapa_atual',
        crontab={'hour': 0, 'minute': 1},
    )
    carregar_call_command(
        '[compras] Notificar Alteração de Etapa',
        'compras_notificar_alteracao_de_etapa',
        crontab={'hour': 1, 'minute': 1},
    )
