from beat.models import Intervalo
from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[ae] Importar CadÚnico',
        'importacao_cadunico',
        interval=[1, Intervalo.HOURS],
    )
    carregar_call_command(
        '[ae] Gerar Bolsas',
        'gerar_bolsas_ae',
        crontab={'hour': 1, 'minute': 7},
    )
    carregar_call_command(
        '[ae] Gerar Bolsas de Pesquisa',
        'gerar_bolsas_ae_pesquisa',
        crontab={'hour': 1, 'minute': 37},
    )
    carregar_call_command(
        '[ae] Gerar Faltas de Alimentação',
        'gera_faltas_alimentacao',
        crontab={'hour': 2, 'minute': 7},
    )
    carregar_call_command(
        '[ae] Verificar Disponibilidade de Bolsas',
        'ofertabolsa_ae_verificar_disponibilidade',
        crontab={'hour': 2, 'minute': 37},
    )
    carregar_call_command(
        '[ae] Gerar Solicitações de Comprovantes Mensais',
        'gera_solicitacoes_comprovantes_mensais',
        crontab={'hour': 3, 'minute': 7},
    )
    carregar_call_command(
        '[edu] Inativar Participações de Assistência Estudantil',
        'edu_inativar_participacao_ae',
        crontab={'hour': 3, 'minute': 37},
    )
