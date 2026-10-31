from djtools.apps import SuapAppConfig as AppConfig


class PortariaConfig(AppConfig):
    default = True
    name = 'portaria'
    verbose_name = 'Visitantes'
    description = 'Controla o acesso de usuários visitantes à estrutura física da instituição, assim como o controle do compartilhamento de wi-fi.'
    area = 'Administração'
    icon = 'door-open'
