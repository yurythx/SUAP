from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[pgd] Sincronizar Permissões da Comissão',
        'sincronizar_permissoes_comissao_pgd',
        crontab={'hour': 5, 'minute': 7},
    )
