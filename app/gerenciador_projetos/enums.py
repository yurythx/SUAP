from model_utils import Choices


class VisibilidadeProjeto:
    PRIVADO = 'Privado'
    PUBLICO = 'Público'

    choices = Choices((PRIVADO, 'privado', 'Privado'), (PUBLICO, 'publico', 'Público'))


class PrioridadeTarefa:
    ALTA = '1'
    MEDIA = '2'
    BAIXA = '3'

    choices = Choices((ALTA, 'alta', 'Alta'), (MEDIA, 'media', 'Média'), (BAIXA, 'baixa', 'Baixa'))


class SituacaoTarefa:
    ABERTA = 1
    EM_ANDAMENTO = 2
    CONCLUIDA = 3
    SUSPENSA = 4
    CANCELADA = 5
    EM_ANALISE = 6

    choices = Choices(
        (ABERTA, 'aberta', 'Aberta'),
        (EM_ANDAMENTO, 'andamento', 'Em andamento'),
        (EM_ANALISE, 'analise', 'Em análise'),
        (SUSPENSA, 'suspensa', 'Suspensa'),
        (CONCLUIDA, 'concluida', 'Concluída'),
        (CANCELADA, 'cancelada', 'Cancelada'),
    )


class SituacaoProjeto:
    ABERTO = 1
    EM_ANDAMENTO = 2
    CONCLUIDO = 3
    SUSPENSO = 4
    CANCELADO = 5

    choices = Choices(
        (ABERTO, 'aberto', 'Aberto'),
        (EM_ANDAMENTO, 'andamento', 'Em andamento'),
        (CONCLUIDO, 'concluido', 'Concluído'),
        (SUSPENSO, 'suspenso', 'Suspenso'),
        (CANCELADO, 'cancelado', 'Cancelado'),
    )


class TipoRecorrencia:
    DIARIAMENTE = 1
    SEMANALMENTE = 2
    MENSALMENTE = 3
    ANUALMENTE = 4

    choices = Choices((DIARIAMENTE, 'Diariamente'), (SEMANALMENTE, 'Semanalmente'), (MENSALMENTE, 'Mensalmente'), (ANUALMENTE, 'Anualmente'))


class DiaDaSemana:
    SEG = 0
    TER = 1
    QUA = 2
    QUI = 3
    SEX = 4
    SAB = 5
    DOM = 6

    choices = Choices(
        (SEG, 'Segunda-feira'),
        (TER, 'Terça-feira'),
        (QUA, 'Quarta-feira'),
        (QUI, 'Quinta-feira'),
        (SEX, 'Sexta-feira'),
        (SAB, 'Sábado'),
        (DOM, 'Domingo'),
    )


class MesDoAno:
    JAN = 1
    FEV = 2
    MAR = 3
    ABR = 4
    MAI = 5
    JUN = 6
    JUL = 7
    AGO = 8
    SET = 9
    OUT = 10
    NOV = 11
    DEZ = 12

    choices = Choices(
        (JAN, 'Janeiro'),
        (FEV, 'Fevereiro'),
        (MAR, 'Março'),
        (ABR, 'Abril'),
        (MAI, 'Maio'),
        (JUN, 'Junho'),
        (JUL, 'Julho'),
        (AGO, 'Agosto'),
        (SET, 'Setembro'),
        (OUT, 'Outubro'),
        (NOV, 'Novembro'),
        (DEZ, 'Dezembro'),
    )
