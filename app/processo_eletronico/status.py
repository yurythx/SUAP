from model_utils import Choices


class NotificacaoStatus:
    STATUS_ESPERANDO = 1
    STATUS_DEFERIDA = 2
    STATUS_INDEFERIDA = 3
    STATUS_CANCELADA = 4

    STATUS_CHOICES = Choices(
        (STATUS_ESPERANDO, 'Pendente', 'Pendente'),
        (STATUS_DEFERIDA, 'Deferida', 'Deferida'),
        (STATUS_INDEFERIDA, 'Indeferida', 'Indeferida'),
        (STATUS_CANCELADA, 'Cancelada', 'Cancelada'),
    )


class SolicitacaoJuntadaStatus:
    STATUS_ESPERANDO = 1  # Nao coloca o processo em tramite
    STATUS_CONCLUIDO = 2  # Nao coloca o processo em tramite
    STATUS_FINALIZADO = 3  # Coloca o processo em tramite
    STATUS_EXPIRADO = 4  # Coloca o processo em tramite
    # STATUS_REJEITADO = 5
    # STATUS_EM_HOMOLOGACAO = 6
    STATUS_CANCELADO = 7  # Coloca o processo em tramite

    STATUS_CHOICES = Choices(
        # Recebe essa siatução quando acaba de ser cadastrado
        # Solicitação está no prazo para que se submeta documentos para que sua juntada seja avaliada
        # O processo para de "Em Tramite" para "Aguardando juntada de documentos"
        (STATUS_ESPERANDO, 'Pendente', 'Pendente'),
        # Quando quem recebeu a solicitação de juntada adiciona um ou mais documentos e após isso conclui a solicitação
        # O processo passa de "Aguardando juntada de documentos" para "Em validação de juntada de documentos"
        (STATUS_CONCLUIDO, 'Concluída pelo solicitado', 'Concluída pelo solicitado'),
        # Quando quem solicitou a juntada avalia os documentos adicionados a solicitação de juntada
        # OU
        # Quando o solicitado conclui a solicitação de juntada sem que adicione algum documento
        #
        # Após essa avaliação ou conclusão o processo passa de "Aguardando juntada de documentos" para "Em Tramite"
        (STATUS_FINALIZADO, 'Finalizada', 'Finalizada'),
        # Quando quem recebeu a solicitação perde o prazo de atender a solicitação (não adicionou documento a solicitação)
        # O processo passa para "Em Tramite"
        (STATUS_EXPIRADO, 'Expirada', 'Expirada'),
        # TODO esse trecho vai ficar comentada ateh que possa ser excluida de forma definitiva
        # (STATUS_REJEITADO, u'Rejeitada', u'Rejeitada'),
        # (STATUS_EM_HOMOLOGACAO, u'Em validação de juntada de documentos', u'Em validação de juntada de documentos'),
        # Quando quem solicitou cancela uma solicitação "Pendente"
        # O processo para de "Aguardando juntada de documentos" para "Em Tramite"
        (STATUS_CANCELADO, 'Cancelada', 'Cancelada'),
    )


class SolicitacaoJuntadaDocumentoStatus:
    STATUS_ESPERANDO = 1
    STATUS_DEFERIDO = 2
    STATUS_INDEFERIDO = 3

    STATUS_CHOICES = Choices(
        (STATUS_ESPERANDO, 'Pendente', 'Pendente'), (STATUS_INDEFERIDO, 'Indeferida', 'Indeferida'), (STATUS_DEFERIDO, 'Deferida', 'Deferida')
    )


class ProcessoStatus:
    STATUS_ATIVO = 1
    STATUS_ARQUIVADO = 2
    STATUS_SOBRESTADO = 3
    STATUS_FINALIZADO = 4
    STATUS_ANEXADO = 5
    STATUS_REABERTO = 6
    STATUS_AGUARDANDO_CIENCIA = 7
    STATUS_AGUARDANDO_JUNTADA = 8
    STATUS_EM_HOMOLOGACAO = 9
    STATUS_EM_TRAMITE_EXTERNO = 10

    STATUS_CHOICES = Choices(
        (STATUS_ATIVO, 'Em trâmite'),
        #
        (STATUS_AGUARDANDO_CIENCIA, 'Aguardando ciência', 'Aguardando ciência'),
        (STATUS_AGUARDANDO_JUNTADA, 'Aguardando juntada de documentos', 'Aguardando juntada de documentos'),
        (STATUS_EM_HOMOLOGACAO, 'Em validação de juntada de documentos', 'Em validação de juntada de documentos'),
        (STATUS_EM_TRAMITE_EXTERNO, 'Em trâmite externo', 'Em trâmite externo'),
        #
        (STATUS_ARQUIVADO, 'Arquivado', 'Arquivado'),
        (STATUS_SOBRESTADO, 'Sobrestado', 'Sobrestado'),
        (STATUS_FINALIZADO, 'Finalizado', 'Finalizado'),
        (STATUS_ANEXADO, 'Anexado', 'Anexado'),
        (STATUS_REABERTO, 'Reaberto', 'Reaberto'),
    )

    @classmethod
    def status_pendentes(cls):
        return [cls.STATUS_AGUARDANDO_CIENCIA, cls.STATUS_AGUARDANDO_JUNTADA, cls.STATUS_EM_HOMOLOGACAO]

    @classmethod
    def status_ativos(cls):
        return [cls.STATUS_ATIVO, cls.STATUS_REABERTO]


class CienciaStatus:
    STATUS_ESPERANDO = 1  # Nao coloca o processo em tramite
    STATUS_CIENTE = 2  # Coloca o processo em tramite
    STATUS_CONSIDERADO_CIENTE = 3  # Coloca o processo em tramite
    STATUS_CANCELADA = 4  # Coloca o processo em tramite

    STATUS_CHOICES = Choices(
        (STATUS_ESPERANDO, 'Aguardando ciência', 'Aguardando ciência'),
        (STATUS_CIENTE, 'Ciente', 'Ciente'),
        (STATUS_CONSIDERADO_CIENTE, 'Considerado Ciente', 'Considerado Ciente'),
        (STATUS_CANCELADA, 'Cancelada', 'Cancelada'),
    )


class SolicitacaoAlteracaoNivelAcessoStatus:
    SITUACAO_SOLICITADO = 1
    SITUACAO_DEFERIDO = 2
    SITUACAO_INDEFERIDO = 3
    SITUACAO_CHOICES = [[SITUACAO_SOLICITADO, 'Solicitado'], [SITUACAO_DEFERIDO, 'Deferido'], [SITUACAO_INDEFERIDO, 'Indeferido']]
