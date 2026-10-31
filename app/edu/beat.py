from beat.models import Intervalo
from beat.utils import carregar_call_command


def load_tasks_schedule():
    carregar_call_command(
        '[edu] Sincronizar Assinatura Digital',
        'edu_sincronizar_assinatura_digital',
        interval=[15, Intervalo.MINUTES],
    )
    carregar_call_command(
        '[edu] Importar Dados',
        'edu_importar_dados',
        crontab={'hour': 1, 'minute': 7},
    )
    carregar_call_command(
        '[edu] Importar Digitais',
        'edu_importar_digitais',
        crontab={'hour': 1, 'minute': 37},
    )
    carregar_call_command(
        '[edu] Importar Fotos',
        'edu_importar_fotos',
        crontab={'hour': 2, 'minute': 7},
    )
    carregar_call_command(
        '[edu] Importar Professores',
        'edu_importar_professores',
        crontab={'hour': 2, 'minute': 37},
    )
    carregar_call_command(
        '[edu] Checar Nada Consta',
        'edu_checar_nada_consta',
        crontab={'hour': 3, 'minute': 7},
    )
    carregar_call_command(
        '[edu] Fechar Período',
        'edu_fechar_periodo',
        crontab={'hour': 3, 'minute': 37},
    )
    carregar_call_command(
        '[edu] Notificar Pendências aos Secretários',
        'edu_notificar_pendencias_secretarios',
        crontab={'hour': 4, 'minute': 7},
    )
    carregar_call_command(
        '[edu] Processar Pedidos de Matrícula',
        'edu_processar_pedidos_matricula',
        crontab={'hour': 4, 'minute': 37},
    )
    carregar_call_command(
        '[edu] Zipar Fotos dos Alunos',
        'edu_zip_fotos_alunos',
        crontab={'hour': 5, 'minute': 7},
    )
    carregar_call_command(
        '[edu] Apagar Usuários de Minicursos',
        'edu_apagar_usuarios_minicursos',
        crontab={'hour': 5, 'minute': 37},
    )
    carregar_call_command(
        '[edu] Gerar Auditoria de Ensino',
        'edu_gerar_auditoria_ensino',
        crontab={'hour': 6, 'minute': 7},
    )
    carregar_call_command(
        '[edu] Fechar Registro Educacenso',
        'edu_fechar_registroeducacenso',
        crontab={'hour': 2, 'minute': 10},
    )
    carregar_call_command(
        '[edu] Arquivar requerimentos expirados',
        'edu_arquivar_requerimentos_expirados',
        crontab={'hour': 2, 'minute': 30},
    )

    carregar_call_command(
        '[edu] Importar Notas do Moodle',
        'edu_importar_notas_moodle',
        crontab={'hour': 3, 'minute': 30},
    )
