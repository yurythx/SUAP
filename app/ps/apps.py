from djtools.apps import SuapAppConfig as AppConfig


class PsConfig(AppConfig):
    default = True
    name = 'ps'
    verbose_name = 'Processos Seletivos (Antigo)'
    description = 'Gerencia os candidatos aprovados no processo seletivo e as filas de convocações. Não é mais utiizado.'
    icon = 'user-edit'
    area = 'Ensino'
