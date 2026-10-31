from djtools.apps import SuapAppConfig as AppConfig


class EleicaoConfig(AppConfig):
    default = True
    name = 'eleicao'
    verbose_name = 'Eleições'
    description = 'Gerencia eleições internas na instituição. O módulo foi desenvolvido inicialmente para atender às eleições da CPA.'
    icon = 'vote-yea'
    area = 'Administração'
