from djtools.apps import SuapAppConfig as AppConfig


class AcompanhamentoFuncionalConfig(AppConfig):
    default = True
    name = 'acompanhamentofuncional'
    verbose_name = 'Acompanhamento Funcional'
    description = 'É responsável por gerir as informações sobre o servidor que está em exercício externo. As principais informações gerenciadas são as frequências e prazo para o servidor retornar ao IFRN.'
    icon = 'user-cog'
    area = 'Gestão de Pessoas'
