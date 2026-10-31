from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[progressao_docente] Docentes a Progredir',
        'docentes_a_progredir',
        crontab={'hour': 2, 'minute': 7},
    )
    carregar_call_command(
        '[progressao_docente] Alerta de Emails de Avaliações',
        'alerta_emails_avaliacoes',
        crontab={'hour': 2, 'minute': 37},
    )
    carregar_call_command(
        '[progressao_docente] Processar Prazos de Avaliação',
        'processar_prazos_avaliacao',
        crontab={'hour': 3, 'minute': 7},
    )
