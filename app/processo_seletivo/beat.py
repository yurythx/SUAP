from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[processo_seletivo] Enviar Notificações de Matrícula',
        'processo_seletivo_enviar_notificacoes_matricula',
        crontab={'hour': 1, 'minute': 7},
    )
