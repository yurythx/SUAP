from djtools.apps import SuapAppConfig as AppConfig


class PitRitV2Config(AppConfig):
    default = True
    name = 'pit_rit_v2'
    verbose_name = 'Plano Individual de Trabalho / Relatório Individual de Trabalho (a partir de 2019)'
    area = 'Ensino'
    description = (
        'Permite ao professor informar o plano e relatório das atividades docentes. Deve ser utilizado para registrar atividades a partir de 2019.'
    )
    icon = 'file-alt'
