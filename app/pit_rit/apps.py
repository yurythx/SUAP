from djtools.apps import SuapAppConfig as AppConfig


class PitRitConfig(AppConfig):
    default = True
    name = 'pit_rit'
    verbose_name = 'Plano Individual de Trabalho / Relatório Individual de Trabalho (até 2019)'
    area = 'Ensino'
    description = 'Permite ao professor informar o plano e relatório das atividades docentes. Deve ser utilizado para registrar atividades até 2019.'
    icon = 'file-alt'
