from djtools.apps import SuapAppConfig as AppConfig


class PesquisaConfig(AppConfig):
    default = True
    name = 'pesquisa'
    verbose_name = 'Pesquisa'
    description = 'Gerencia os projetos de pesquisa e a submissão de obras para a Editora.'
    icon = 'atlas'
    area = 'Pesquisa e Inovação'
