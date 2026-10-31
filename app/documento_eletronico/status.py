from model_utils import Choices


class DocumentoStatus:
    STATUS_RASCUNHO = 1
    STATUS_CONCLUIDO = 2
    STATUS_EM_REVISAO = 3
    STATUS_REVISADO = 4
    STATUS_AGUARDANDO_ASSINATURA = 5
    STATUS_ASSINADO = 6
    STATUS_FINALIZADO = 7
    STATUS_CANCELADO = 8

    STATUS_CHOICES = Choices(
        (STATUS_RASCUNHO, 'Rascunho', 'Rascunho'),
        (STATUS_CONCLUIDO, 'Concluído', 'Concluído'),
        (STATUS_EM_REVISAO, 'Em Revisão', 'Em Revisão'),
        (STATUS_REVISADO, 'Revisado', 'Revisado'),
        (STATUS_CANCELADO, 'Cancelado', 'Cancelado'),
        (STATUS_AGUARDANDO_ASSINATURA, 'Aguardando assinatura', 'Aguardando assinatura'),
        (STATUS_ASSINADO, 'Assiando', 'Assinado'),
        (STATUS_FINALIZADO, 'Finalizado', 'Finalizado'),
    )


class SolicitacaoStatus:
    STATUS_ESPERANDO = 1
    STATUS_DEFERIDA = 2
    STATUS_INDEFERIDA = 3

    STATUS_CHOICES = Choices(
        (STATUS_ESPERANDO, 'Aguardando', 'Aguardando'), (STATUS_INDEFERIDA, 'Indeferida', 'Indeferida'), (STATUS_DEFERIDA, 'Deferida', 'Deferida')
    )


# TODO: Remover este classe e usar trazer para cá o enum NivelAcesso presente em documento_eletronico.models.
class NivelAcesso:
    NIVEL_ACESSO_SIGILOSO = 1
    NIVEL_ACESSO_RESTRITO = 2
    NIVEL_ACESSO_PUBLICO = 3

    NIVEL_ACESSO_CHOICES = ((NIVEL_ACESSO_SIGILOSO, 'Sigiloso'), (NIVEL_ACESSO_RESTRITO, 'Restrito'), (NIVEL_ACESSO_PUBLICO, 'Público'))


class AvaliacaoSolicitacaoStatus:
    STATUS_ESPERANDO = 1
    STATUS_DEFERIDA = 2
    STATUS_INDEFERIDA = 3

    STATUS_CHOICES = Choices(
        (STATUS_ESPERANDO, 'Aguardando avaliação', 'Aguardando avaliação'),
        (STATUS_DEFERIDA, 'Deferida', 'Deferida'),
        (STATUS_INDEFERIDA, 'Rejeitada', 'Rejeitada'),
    )
