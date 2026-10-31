from beat.models import Intervalo
from beat.utils import carregar_bash_script, carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[comum] Remover grupos de usuários inativos',
        'remover_grupos_usuarios_inativos',
        crontab={'hour': 0, 'minute': 7},
    )
    carregar_call_command(
        '[comum] Test Command',
        'test_command',
        args=['migrations and tasks', '--all'],
        kwargs={'verbosity': 0, 'wait': 10},
        interval=[1, Intervalo.MINUTES],
        expire_seconds=30,
    )
    carregar_bash_script(
        '[comum] Date Test',
        'date',
        interval=[1, Intervalo.MINUTES],
        expire_seconds=30,
    )
    carregar_bash_script(
        '[comum] TMPReaper',
        'tmpreaper',
        args=['4h', '/tmp', '--showdeleted'],
        interval=[4, Intervalo.HOURS],
        expire_seconds=300,
    )
    carregar_call_command(
        '[comum] Sync Emails',
        'sync_emails',
        crontab={'hour': 1, 'minute': 37},
    )
    carregar_call_command(
        '[comum] Limpar Index Layout',
        'limpar_index_layout',
        crontab={'hour': 2, 'minute': 7},
    )
    carregar_call_command(
        '[comum] Limpar Sessões do SUAP',
        'clearsessions_suap',
        crontab={'hour': 2, 'minute': 37},
    )
    carregar_call_command(
        '[comum] Limpar Tasks do Celery',
        'clean_tasks',
        crontab={'hour': 3, 'minute': 7},
    )
    carregar_call_command(
        '[comum] Remover Permissão de Usuários',
        'remover_permissao_usuarios',
        crontab={'hour': 3, 'minute': 37},
    )
    carregar_call_command(
        '[comum] Indeferir Solicitações de Reserva de Sala',
        'indeferir_solicitacoes_reserva_sala',
        crontab={'hour': 4, 'minute': 7},
    )
    carregar_call_command(
        '[comum] Zipar Fotos dos Funcionários',
        'zip_fotos_funcionarios',
        crontab={'hour': 4, 'minute': 37},
    )
    carregar_call_command(
        '[comum] Desativar APIs Inacessíveis',
        'desativar_apis_inacessiveis',
        interval=[15, Intervalo.MINUTES],
        expire_seconds=30,
    )
