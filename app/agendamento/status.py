from model_utils import Choices


class SolicitacaoAgendamentoStatus:
    STATUS_ESPERANDO = 1
    STATUS_DEFERIDA = 2
    STATUS_INDEFERIDA = 3
    STATUS_CANCELADA = 4
    STATUS_FINALIZADO = 5

    STATUS_CHOICES = Choices(
        (STATUS_ESPERANDO, 'Aguardando análise', 'Aguardando análise'),
        (STATUS_INDEFERIDA, 'Indeferida', 'Indeferida'),
        (STATUS_DEFERIDA, 'Deferida', 'Deferida'),
        (STATUS_CANCELADA, 'Cancelada', 'Cancelada'),
        (STATUS_FINALIZADO, 'Finalizado', 'Finalizado'),
    )


class AgendamentoStatus:
    STATUS_INATIVO = 0
    STATUS_ATIVO = 1
    STATUS_FINALIZADO = 2

    STATUS_CHOICES = Choices(
        (STATUS_ATIVO, 'Ativo', 'Ativo'), (STATUS_INATIVO, 'Inativo', 'Inativo'), (STATUS_FINALIZADO, 'Finalizado', 'Finalizado')
    )
