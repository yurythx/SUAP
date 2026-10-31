from djtools.apps import SuapAppConfig as AppConfig


class ContratosConfig(AppConfig):
    default = True
    name = 'contratos'
    verbose_name = 'Contratos'
    description = """
                    Módulo responsável por Gerenciar o ciclo de vidas dos contratos da instituição a partir da sua publicação.
                    Dentro do módulo é possível gerenciar o cronograma do contrato assim como as suas parcelas, realizar
                    as medições contratuais e informar as ocorrências durante a vigência do contrato
                  """
    icon = 'file-contract'
    area = 'Administração'
