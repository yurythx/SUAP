from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[projetos] Notifica Atrasos',
        'notifica_atrasos_projetos',
        crontab={'hour': 3, 'minute': 7},
    )
    carregar_call_command(
        '[projetos] Gerencia Prazos Indicações Avaliadores',
        'gerencia_prazos_indicacoes_avaliadores_extensao',
        crontab={'hour': 2, 'minute': 7},
    )
