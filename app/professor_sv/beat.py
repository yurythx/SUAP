from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[professor_sv] Manutenção das vagas e contratos',
        'psv_manutencao_vagas_contratos',
        crontab={'hour': 5, 'minute': 7},
    )
