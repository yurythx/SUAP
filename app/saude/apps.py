from djtools.apps import SuapAppConfig as AppConfig


class SaudeConfig(AppConfig):
    default = True
    name = 'saude'
    verbose_name = 'Saúde'
    icon = 'heartbeat'
    area = 'Atividades Estudantis'
    description = 'Gerencia os atendimentos relativos à área de Saúde a partir das seguintes especializações: Médico-Enfermagem, Odontologia, Psicologia, Fisioterapia e Nutrição.'
