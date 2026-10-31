from djtools.apps import SuapAppConfig as AppConfig


class EtepConfig(AppConfig):
    default = True
    name = 'etep'
    verbose_name = 'ETEP'
    area = 'Ensino'
    description = 'Realiza o acompanhamento de alunos pela Equipe Técnico Pedagógica.'
    icon = 'user-tag'
