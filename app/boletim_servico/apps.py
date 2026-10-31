from djtools.apps import SuapAppConfig as AppConfig


class BoletimServicoConfig(AppConfig):
    default = True
    name = 'boletim_servico'
    verbose_name = 'Boletim de Serviços'
    description = 'Emite boletim com os atos (portarias, resoluções e outros) de gestão da instituição.'
    icon = 'file-contract'
    area = 'Gestão de Pessoas'
