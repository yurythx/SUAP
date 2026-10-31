from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[gestao] Processar Variáveis',
        'processar_variaveis',
        crontab={'hour': 4, 'minute': 37},
    )
