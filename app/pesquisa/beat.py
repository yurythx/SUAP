from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[pesquisa] Importar Serviços RPI',
        'importar_servicos_rpi',
        crontab={'hour': '12', 'minute': '0', 'day_of_week': '3,5'},
    )
    carregar_call_command(
        '[pesquisa] Importar Serviços RPI de Softwares',
        'importar_servicos_rpi_softwares',
        crontab={'hour': '18', 'minute': '0', 'day_of_week': '3,5'},
    )
    carregar_call_command(
        '[pesquisa] Importar Serviços RPI DI',
        'importar_servicos_rpi_di',
        crontab={'hour': '19', 'minute': '0', 'day_of_week': '3,5'},
    )
    carregar_call_command(
        '[pesquisa] Normaliza Pontuações Editais',
        'normaliza_pontuacoes_editais_pesquisa',
        crontab={'hour': 1, 'minute': 7},
    )
    carregar_call_command(
        '[pesquisa] Notifica Atrasos',
        'notifica_atrasos_projetos_pesquisa',
        crontab={'hour': 1, 'minute': 37},
    )
    carregar_call_command(
        '[pesquisa] Gerencia Prazos Indicações Avaliadores',
        'gerencia_prazos_indicacoes_avaliadores',
        crontab={'hour': 2, 'minute': 7},
    )
    carregar_call_command(
        '[pesquisa] Notificar Atraso de Parecer de Obra',
        'notificar_atraso_parecer_obra',
        crontab={'hour': 2, 'minute': 37},
    )
    carregar_call_command(
        '[pesquisa] Importar RPI',
        'importar_rpi',
        crontab={'hour': 3, 'minute': 7},
    )
    carregar_call_command(
        '[pesquisa] Importar RPI Software',
        'importar_rpi_software',
        crontab={'hour': 3, 'minute': 37},
    )
