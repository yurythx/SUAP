from djtools.apps import SuapAppConfig as AppConfig


class CatalogoProvedorServicoConfig(AppConfig):
    default = True
    name = 'catalogo_provedor_servico'
    verbose_name = 'Balcão Digital'
    description = 'Gerencia os serviços do Balcão Digital.'
    icon = 'check-circle'
    area = 'Comum'
