from djtools.apps import SuapAppConfig as AppConfig


class PdpV2Config(AppConfig):
    default = True
    name = 'pdp_ifrn'
    verbose_name = 'PDP (v2) - Plano de Desenvolvimento Pessoal'
    area = 'Gestão de Pessoas'
