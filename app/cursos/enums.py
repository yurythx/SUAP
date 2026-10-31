class TipoCurso:
    CONCURSO = 1
    CURSO = 2
    ATIVIDADE_EXTERNA = 3

    @classmethod
    def get_choices(cls):
        return [[cls.CONCURSO, 'Concurso'], [cls.CURSO, 'Curso'], [cls.ATIVIDADE_EXTERNA, 'Atividade Externa']]


class SituacaoCurso:
    NAO_INICIADO = 0
    INICIADO = 1
    FINALIZADO = 2
    AGUARDANDO_CADASTRO_EM_FOLHA = 3
    CADASTRADO_EM_FOLHA = 4

    @classmethod
    def get_choices(cls):
        return [
            [cls.NAO_INICIADO, 'Não iniciado'],
            [cls.INICIADO, 'Iniciado'],
            [cls.AGUARDANDO_CADASTRO_EM_FOLHA, 'Aguardando Cadastro em Folha'],
            [cls.CADASTRADO_EM_FOLHA, 'Cadastrado em Folha'],
            [cls.FINALIZADO, 'Finalizado'],
        ]

    @classmethod
    def curso_em_andamento(cls):
        return [cls.INICIADO, cls.AGUARDANDO_CADASTRO_EM_FOLHA]

    @classmethod
    def curso_concluido(cls):
        return [cls.CADASTRADO_EM_FOLHA, cls.FINALIZADO]


class SituacaoParticipante:
    LIBERADO = 0
    NAO_LIBERADO = 1
    AGUARDANDO_LIBERACAO = 2
    PENDENTE = 3

    @classmethod
    def get_choices(cls):
        return [
            [cls.AGUARDANDO_LIBERACAO, 'Aguardando Liberação'],
            [cls.LIBERADO, 'Deferido'],
            [cls.NAO_LIBERADO, 'Indeferido'],
            [cls.PENDENTE, 'Pendente de Pagamento'],
        ]

    @classmethod
    def participante_em_atividade(cls):
        return [cls.LIBERADO, cls.PENDENTE]


class SituacaoDetalhamentoAtividadeParticipante:
    INDEFINIDO = 0
    AGUARDANDO_PREENCHIMENTO = 1
    AGUARDANDO_AVALIACAO = 2
    DEFERIDO = 3

    # uma situação 'INDEFERIDO' não cabe aqui ... uma vez liberado, o participante
    # precisa concluir as etapas e não ficar num "limbo" em relação ao detalhamento
    # das horas ... no caso de não deferir o detalhamento, a situação volta para
    # aguardando preenchimento.

    @classmethod
    def get_choices(cls):
        return [
            [cls.INDEFINIDO, 'Indefinido ou não aplicável'],
            [cls.AGUARDANDO_PREENCHIMENTO, 'Aguardando Preenchimento'],
            [cls.AGUARDANDO_AVALIACAO, 'Aguardando Avaliação'],
            [cls.DEFERIDO, 'Deferido'],
        ]

    @classmethod
    def detalhamento_pendente(cls):
        return [cls.AGUARDANDO_PREENCHIMENTO, cls.AGUARDANDO_AVALIACAO]
