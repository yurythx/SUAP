from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[beat] Limpar Resultados de Execução',
        'limpar_resultado_execucao',
        kwargs={'days': 30},
        crontab={
            'minute': 0,
            'hour': 10,
        },
    )
