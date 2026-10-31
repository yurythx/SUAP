from djtools.apps import SuapAppConfig as AppConfig


class ArquivoConfig(AppConfig):
    default = True
    name = 'arquivo'
    verbose_name = 'Arquivo'
    description = 'É responsável pelo cadastro e fluxo de validação dos arquivos do assentamento funcional. Esses dados podem ser vistos na pasta funcional do servidor presente no perfil do servidor.'
    icon = 'user-tag'
    area = 'Gestão de Pessoas'
