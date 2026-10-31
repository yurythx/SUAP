from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[pgd2] Sincronizar Permissões da Comissão',
        'sincronizar_permissoes_comissao_pgd2',
        crontab={'hour': 1, 'minute': 2},
    )
    carregar_call_command(
        '[pgd2] Carregar Atualizar relação setor SIAPE x SUAP',
        'carregar_setores_pgd2',
        crontab={'hour': 1, 'minute': 12},
    )
    carregar_call_command(
        '[pgd2] Monitoramento do PGD',
        'monitoramento_pgd2',
        crontab={'hour': 2, 'minute': 22},
    )
    carregar_call_command(
        '[pgd2] Enviar Dados para API',
        'enviar_dados_api_pgd2',
        crontab={'hour': 4, 'minute': 1},
    )
    carregar_call_command(
        '[pgd2] Notificações PGD',
        'notifica_pgd2',
        crontab={'hour': 5, 'minute': 1},
    )
    carregar_call_command(
        '[pgd2] Descartar RITs órfãos do GitLab',
        'descartar_rits_gitlab_orfaos',
        crontab={'hour': 3, 'minute': 17},
    )
