from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[rh] Revogar reativações temporárias vencidas',
        'revogar_reativacoes_temporarias_vencidas',
        crontab={'hour': 0, 'minute': 37},
    )
    carregar_call_command(
        '[rh] Atualizar servidor completo',
        'atualizar_servidor_completo_ws',
        args=['--completo'],
        crontab={'hour': 21, 'minute': 7},
    )
    carregar_call_command(
        '[rh] Importar siape',
        'importar_siape',
        crontab={'hour': 1, 'minute': 7},
    )
    carregar_call_command(
        '[rh] Organizar data fim histórico função',
        'organizar_data_fim_historico_funcao',
        crontab={'hour': 2, 'minute': 7},
    )
    carregar_call_command(
        '[rh] Organizar histórico de setor siape',
        'organizar_historico_setor_siape',
        crontab={'hour': 2, 'minute': 37},
    )
    carregar_call_command(
        '[rh] Organizar data de fim de histórico de setor',
        'organizar_data_fim_historico_setor',
        crontab={'hour': 3, 'minute': 7},
    )
    carregar_call_command(
        '[rh] Importar arquivos SCDP',
        'importar_arquivos_scdp',
        crontab={'hour': 3, 'minute': 37},
    )
    # carregar_call_command(
    #     '[rh] Importar função do servidor',
    #     'importar_funcao_servidor',
    #     crontab={'hour': 4, 'minute': 7},
    # )
    carregar_call_command(
        '[rh] Atualizar sub instances de pessoa física',
        'atualizar_pessoa_fisica_sub_instances',
        crontab={'hour': 4, 'minute': 37},
    )
    carregar_call_command(
        '[rh] Atualizar setor dos prestadores',
        'atualizar_setor_prestador',
        crontab={'hour': 5, 'minute': 7},
    )
    #
    # mapeamento de setores
    carregar_call_command(
        '[rh] Mapear equivalências de setores SUAP com SIAPE',
        'mapear_equivalencias_setor',
        args=['--commit', '--include-already-set', '--overwrite'],
        crontab={'hour': 5, 'minute': 7},
    )
    #
    # sincronização dos códigos SIORG
    carregar_call_command(
        '[rh] Sincronizar códigos SIORG',
        'sincronizar_siorg_setor',
        args=['--commit', '--include-already-set', '--overwrite'],
        crontab={'hour': 5, 'minute': 37},
    )
