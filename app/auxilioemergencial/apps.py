from djtools.apps import SuapAppConfig as AppConfig


class AuxilioEmergencialConfig(AppConfig):
    default = True
    name = 'auxilioemergencial'
    verbose_name = 'Auxílio Emergencial'
    description = 'Gerencia as inscrições para concessão do benefício de Auxílio Emergencial aos alunos.'
    icon = 'virus'
    area = 'Atividades Estudantis'
