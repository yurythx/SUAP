from beat.utils import carregar_call_command


def load_tasks_schedule() -> None:
    """Registra as rotinas periódicas no Celery Beat.

    O ``get_or_create`` de ``carregar_call_command`` cria cada tarefa uma única vez, no
    ``manage.py sync`` do deploy. Depois disso, a cadência que vale é a do registro no admin de
    agendamentos: mudar o ``crontab`` aqui só afeta instalações novas.

    A primeira execução após o deploy processa todo o backlog de bases já publicadas e vencidas:
    rode ``manage.py atualizar_bases_dados_abertos --simular`` em produção antes para dimensioná-lo.

    Os ``expire_seconds`` acompanham as cadências padrão (23h para a diária, 72h para a semanal):
    se a cadência for reduzida no admin, reduza-os junto para não deixar disparos antigos na fila.
    """
    carregar_call_command(
        '[dados_abertos] Atualizar Bases de Dados Abertos',
        'atualizar_bases_dados_abertos',
        crontab={'hour': 2, 'minute': 47},
        expire_seconds=23 * 3600,
    )
    carregar_call_command(
        '[dados_abertos] Notificar Pendências do PDA',
        'notificar_pendencias_dados_abertos',
        crontab={'day_of_week': 1, 'hour': 7, 'minute': 47},
        expire_seconds=72 * 3600,
    )
