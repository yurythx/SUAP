from djtools.apps import SuapAppConfig as AppConfig


class TesouroGerencialConfig(AppConfig):
    default = True
    name = 'tesouro_gerencial'
    verbose_name = 'Tesouro Gerencial'
    description = 'Importa relatórios específicos do Tesouro Gerencial para o SUAP.'
    icon = 'gem'
    area = 'Administração'
