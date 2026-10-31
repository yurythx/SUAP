from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[demandas] Remover Ambientes de Homologação Expirados',
        'remover_ambientes_homolog_expirados',
        crontab={'hour': 3, 'minute': 37},
    )
