class PercentualExecucao:
    p0 = '0%'
    p10 = '10%'
    p20 = '20%'
    p30 = '30%'
    p40 = '40%'
    p50 = '50%'
    p60 = '60%'
    p70 = '70%'
    p80 = '80%'
    p90 = '90%'
    p100 = '100%'

    @classmethod
    def get_choices(cls):
        return [
            [0, cls.p0],
            [10, cls.p10],
            [20, cls.p20],
            [30, cls.p30],
            [40, cls.p40],
            [50, cls.p50],
            [60, cls.p60],
            [70, cls.p70],
            [80, cls.p80],
            [90, cls.p90],
            [100, cls.p100],
        ]


class TipoUnidade:
    CAMPUS = 'Campus'
    DIRETORIA = 'Diretoria Sistêmica'
    PRO_REITORIA = 'Pró-Reitoria'

    @classmethod
    def get_choices(cls):
        return [[cls.CAMPUS, cls.CAMPUS], [cls.DIRETORIA, cls.DIRETORIA], [cls.PRO_REITORIA, cls.PRO_REITORIA]]

    @classmethod
    def get_lista_simples(cls):
        return [cls.CAMPUS, cls.DIRETORIA, cls.PRO_REITORIA]


class TipoRecurso:
    ESTUDANTIL = 'Assistência Estudantil'
    BIBLIOTECA = 'Biblioteca'
    CAMPUS = 'Campus'
    CAPACITACAO = 'Capacitação'
    EAD = 'EaD'
    ENSINO = 'Ensino'
    EXPANSAO = 'Expansão'
    EXTENSAO = 'Extensão'
    FIC = 'FIC'
    PESQUISA = 'Pesquisa'
    PROJETO_ESPECIAL = 'Projeto Especial'
    OUTRA_FONTE = 'Outra Fonte de Captação'
    TI = 'Tecnologia da Informação'

    @classmethod
    def get_choices(cls):
        return [
            [cls.ESTUDANTIL, cls.ESTUDANTIL],
            [cls.BIBLIOTECA, cls.BIBLIOTECA],
            [cls.CAMPUS, cls.CAMPUS],
            [cls.CAPACITACAO, cls.CAPACITACAO],
            [cls.EAD, cls.EAD],
            [cls.ENSINO, cls.ENSINO],
            [cls.EXPANSAO, cls.EXPANSAO],
            [cls.EXTENSAO, cls.EXTENSAO],
            [cls.FIC, cls.FIC],
            [cls.OUTRA_FONTE, cls.OUTRA_FONTE],
            [cls.PESQUISA, cls.PESQUISA],
            [cls.PROJETO_ESPECIAL, cls.PROJETO_ESPECIAL],
            [cls.TI, cls.TI],
        ]

    @classmethod
    def get_choices_empty_label(cls):
        return [
            ['', '---------'],
            [cls.ESTUDANTIL, cls.ESTUDANTIL],
            [cls.BIBLIOTECA, cls.BIBLIOTECA],
            [cls.CAMPUS, cls.CAMPUS],
            [cls.CAPACITACAO, cls.CAPACITACAO],
            [cls.EAD, cls.EAD],
            [cls.ENSINO, cls.ENSINO],
            [cls.EXPANSAO, cls.EXPANSAO],
            [cls.EXTENSAO, cls.EXTENSAO],
            [cls.FIC, cls.FIC],
            [cls.OUTRA_FONTE, cls.OUTRA_FONTE],
            [cls.PESQUISA, cls.PESQUISA],
            [cls.PROJETO_ESPECIAL, cls.PROJETO_ESPECIAL],
            [cls.TI, cls.TI],
        ]

    @classmethod
    def get_lista_simples(cls):
        return [
            cls.CAMPUS,
            cls.BIBLIOTECA,
            cls.CAPACITACAO,
            cls.EAD,
            cls.ENSINO,
            cls.EXPANSAO,
            cls.EXTENSAO,
            cls.FIC,
            cls.PESQUISA,
            cls.ESTUDANTIL,
            cls.PROJETO_ESPECIAL,
            cls.OUTRA_FONTE,
            cls.TI,
        ]


class Situacao:
    DEFERIDA = 'Deferida'
    INDEFERIDA = 'Indeferida'
    PENDENTE = 'Não Avaliada'
    PARCIALMENTE_DEFERIDA = 'Parcialmente Deferida'

    @classmethod
    def get_choices(cls):
        return [
            [cls.DEFERIDA, cls.DEFERIDA],
            [cls.INDEFERIDA, cls.INDEFERIDA],
            [cls.PENDENTE, cls.PENDENTE],
            [cls.PARCIALMENTE_DEFERIDA, cls.PARCIALMENTE_DEFERIDA],
        ]

    @classmethod
    def get_lista_simples(cls):
        return [cls.DEFERIDA, cls.INDEFERIDA, cls.PENDENTE, cls.PARCIALMENTE_DEFERIDA]
