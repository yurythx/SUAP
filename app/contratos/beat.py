from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[contratos] Notificar contratos sem garantia vinculada',
        'notificar_contratos_sem_garantia_vinculada',
        crontab={'hour': 4, 'minute': 7},
    )
    carregar_call_command(
        '[contratos] Notificar contratos a expirar',
        'notificar_contratos_a_expirar',
        crontab={'hour': 4, 'minute': 37},
    )
    carregar_call_command(
        '[contratos] Notificar fiscalização de contratos',
        'notificar_fiscalizacao_contratos',
        crontab={'hour': 5, 'minute': 7},
    )
    carregar_call_command(
        '[contratos] Notificar contratos com mão de obra sem registro',
        'notificar_contratos_sem_mao_de_obra',
        crontab={'hour': 4, 'minute': 52},
    )
