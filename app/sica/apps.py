from djtools.apps import SuapAppConfig as AppConfig


class SicaConfig(AppConfig):
    default = True
    name = 'sica'
    verbose_name = 'SICA'
    description = 'Importa os dados do sistema legado SICA (sistema utilizado antes do QAcadêmico).'
    area = 'Ensino'
