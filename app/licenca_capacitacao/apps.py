from djtools.apps import SuapAppConfig as AppConfig


class LicencaCapacitacaoConfig(AppConfig):
    default = True
    name = 'licenca_capacitacao'
    verbose_name = 'Licença Capacitação'
    area = 'Gestão de Pessoas'
    icon = 'sign-out-alt'
    description = (
        'O Módulo de Licença Capacitação é responsável por gerir todo o processo de submissão e processamento dos pedidos de licença capacitação.'
    )
