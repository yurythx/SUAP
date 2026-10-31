from djtools.apps import SuapAppConfig as AppConfig


class PnpConfig(AppConfig):
    default = True
    name = 'pnp'
    verbose_name = 'PNP'
    description = 'Gerencia os dados da Plataforma Nilo Peçanha (PNP).'
    area = 'Desenvolvimento Institucional'
