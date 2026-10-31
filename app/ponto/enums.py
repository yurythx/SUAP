class TipoLiberacao:
    POR_DOCUMENTO_LEGAL = 'Por Documento Legal'
    EVENTO = 'Evento/Data Comemorativa'
    RECESSO = 'Recesso'
    FERIADO = 'Feriado'
    FERIADO_RECORRENTE = 'Feriado Recorrente'
    LIBERACAO_PARCIAL = 'Liberação Parcial'

    @classmethod
    def get_choices(cls):
        return [
            [0, cls.POR_DOCUMENTO_LEGAL],
            [1, cls.EVENTO],
            [2, cls.RECESSO],
            [3, cls.FERIADO],
            [4, cls.FERIADO_RECORRENTE],
            [5, cls.LIBERACAO_PARCIAL],
        ]

    @classmethod
    def get_status(cls, numero):
        for id, nome in cls.get_choices():
            if id == numero:
                return nome
        return 'Desconhecido'

    @classmethod
    def get_numero(cls, status):
        for id, nome in cls.get_choices():
            if nome == status:
                return id
        return 0


class TipoFormFrequenciaTerceirizados:
    POR_SETOR = 1
    POR_TERCEIRIZADO = 2

    @classmethod
    def get_choices(cls):
        return [[cls.POR_SETOR, 'Por Setor'], [cls.POR_TERCEIRIZADO, 'Por Terceirizado']]
