from ninja import Schema


class SetorSchema(Schema):
    id: int
    codigo: str
    sigla: str
    nome: str
    campus: str
    campus_nome: str
    setor_superior: str
    setor_superior_nome: str

    @staticmethod
    def resolve_id(setor):
        return setor.id

    @staticmethod
    def resolve_codigo(setor):
        return setor.codigo or ''

    @staticmethod
    def resolve_sigla(setor):
        return setor.sigla

    @staticmethod
    def resolve_nome(setor):
        return setor.nome

    @staticmethod
    def resolve_campus(setor):
        return setor.uo.sigla if setor.uo_id else ''

    @staticmethod
    def resolve_campus_nome(setor):
        return setor.uo.nome if setor.uo_id else ''

    @staticmethod
    def resolve_setor_superior(setor):
        return setor.superior.sigla if setor.superior_id else ''

    @staticmethod
    def resolve_setor_superior_nome(setor):
        return setor.superior.nome if setor.superior_id else ''
