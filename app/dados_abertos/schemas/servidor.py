from ninja import Schema


class ServidorSchema(Schema):
    matricula: str
    nome: str
    cargo_emprego: str
    setor: str
    setor_nome: str
    campus: str
    campus_nome: str

    @staticmethod
    def resolve_matricula(servidor):
        return servidor.matricula

    @staticmethod
    def resolve_nome(servidor):
        return servidor.pessoa_fisica.nome

    @staticmethod
    def resolve_cargo_emprego(servidor):
        if not servidor.cargo_emprego_id:
            return ''
        # Normaliza espaços/quebras de linha vindos do banco
        return ' '.join((servidor.cargo_emprego.nome or '').split())

    @staticmethod
    def resolve_setor(servidor):
        return servidor.setor.sigla if servidor.setor_id else ''

    @staticmethod
    def resolve_setor_nome(servidor):
        return servidor.setor.nome if servidor.setor_id else ''

    @staticmethod
    def resolve_campus(servidor):
        return servidor.setor.uo.sigla if servidor.setor and servidor.setor.uo else ''

    @staticmethod
    def resolve_campus_nome(servidor):
        return servidor.setor.uo.nome if servidor.setor and servidor.setor.uo else ''
