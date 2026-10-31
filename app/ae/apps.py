from djtools.apps import SuapAppConfig as AppConfig


class AeConfig(AppConfig):
    default = True
    name = 'ae'
    verbose_name = 'Serviço Social'
    description = (
        'É responsável pelo gerenciamento dos programas de atividades estudantis utilizando dados da caracterização socio-econômica do Aluno.'
    )
    icon = 'graduation-cap'
    area = 'Atividades Estudantis'
