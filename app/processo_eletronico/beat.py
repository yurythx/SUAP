from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[processo_eletronico] Atualizar Status Geral de Processos',
        'processo_eletronico_atualizar_status_geral_processo',
        crontab={'hour': 1, 'minute': 7},
    )
    carregar_call_command(
        '[processo_eletronico] Gerar Números de Processos',
        'processo_eletronico_gerar_numeros',
        crontab={'hour': 1, 'minute': 37},
    )
    carregar_call_command(
        '[processo_eletronico] Atualizar Permissões de Processos',
        'processo_eletronico_atualizar_permissoes',
        crontab={'hour': 2, 'minute': 7},
    )
    carregar_call_command(
        '[processo_eletronico] Checar Prazos de Recebimento de Processos',
        'processo_eletronico_checar_prazos_recebimento',
        crontab={'hour': 2, 'minute': 37},
    )
