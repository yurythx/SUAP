from beat.models import Intervalo
from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[plan_estrategico] Conferir Requisição de Movimentação SIAFI',
        'plan_estrategico_conferir_requisicao_movimentacao_siafi',
        interval=[1, Intervalo.HOURS],
    )
    carregar_call_command(
        '[plan_estrategico] Conferir Requisição de Ajuste Interno SIAFI',
        'plan_estrategico_conferir_requisicao_ajuste_interno_siafi',
        interval=[1, Intervalo.HOURS],
    )
    carregar_call_command(
        '[plan_estrategico] Validar Empenhos',
        'plan_estrategico_validar_empenhos',
        interval=[1, Intervalo.HOURS],
    )
    carregar_call_command(
        '[plan_estrategico] Coletar Variáveis do Ensino',
        'plan_estrategico_coletar_variaveis_edu',
        crontab={'hour': 1, 'minute': 7},
    )
    carregar_call_command(
        '[plan_estrategico] Coletar Variáveis da Gestão',
        'plan_estrategico_coletar_variaveis_gestao',
        crontab={'hour': 1, 'minute': 37},
    )
    carregar_call_command(
        '[plan_estrategico] Coletar Variáveis da Extensão',
        'plan_estrategico_coletar_variaveis_extensao',
        crontab={'hour': 2, 'minute': 7},
    )
    carregar_call_command(
        '[plan_estrategico] Coletar Variáveis da Gestão de Pessoas',
        'plan_estrategico_coletar_variaveis_gestao_pessoas',
        crontab={'hour': 2, 'minute': 37},
    )
    carregar_call_command(
        '[plan_estrategico] Coletar Variáveis da Pesquisa',
        'plan_estrategico_coletar_variaveis_pesquisa',
        crontab={'hour': 3, 'minute': 7},
    )
    carregar_call_command(
        '[plan_estrategico] Coletar Variáveis da Pesquisa em Rede',
        'plan_estrategico_coletar_variaveis_pesquisa_rede',
        crontab={'hour': 3, 'minute': 37},
    )
    carregar_call_command(
        '[plan_estrategico] Coletar Variáveis do Tesouro Gerencial',
        'plan_estrategico_coletar_variaveis_tesouro_gerencial',
        crontab={'hour': 4, 'minute': 7},
    )
    carregar_call_command(
        '[plan_estrategico] Coletar Variáveis do Pós-Período',
        'plan_estrategico_coletar_variaveis_pos_periodo',
        crontab={'hour': 4, 'minute': 37},
    )
    carregar_call_command(
        '[plan_estrategico] Coletar Variáveis da Extensão em Rede',
        'plan_estrategico_coletar_variaveis_extensao_rede',
        crontab={'hour': 5, 'minute': 7},
    )
    carregar_call_command(
        '[plan_estrategico] Totalizar Indicadores',
        'plan_estrategico_totalizar_indicadores',
        crontab={'hour': 5, 'minute': 37},
    )
    carregar_call_command(
        '[plan_estrategico] Notificar Preenchimento de Variáveis',
        'notifica_preenchimento_variaveis',
        crontab={'hour': 6, 'minute': 7},
    )
    carregar_call_command(
        '[plan_estrategico] Atualizar Valores de Indicadores',
        'plan_estrategico_atualizar_valores_indicadores',
        crontab={'hour': 6, 'minute': 37},
    )
    carregar_call_command(
        '[plan_estrategico] Atualizar Valores Trimestrais',
        'plan_estrategico_atualizar_valores_trimestrais',
        crontab={'hour': 7, 'minute': 7},
    )
