from beat.models import Intervalo
from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[cnpq] Importar Dados CNPq',
        'cnpq_importar',
        args=['--xml'],
        crontab={'hour': 19, 'minute': 1},
    )
    carregar_call_command(
        '[cnpq] Atualizar Grupos de Pesquisa dos Servidores',
        'atualizar_grupos_pesquisa_dos_servidores',
        interval=[1, Intervalo.HOURS],
    )
    carregar_call_command(
        '[cnpq] Atualizar Datas do Servidor',
        'atualizar_datas_do_servidor',
        crontab={'hour': 1, 'minute': 7},
    )
