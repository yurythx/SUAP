from djtools.apps import SuapAppConfig as AppConfig


class AvaliacaoIntegradaConfig(AppConfig):
    default = True
    name = 'avaliacao_integrada'
    verbose_name = 'Avaliação Integrada'
    description = 'Gerencia a Avaliação Integrada.'
    icon = 'percentage'
    area = 'Desenvolvimento Institucional'
