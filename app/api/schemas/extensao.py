import datetime

from ninja import Schema


class ProjetoSchema(Schema):
    content_type: str
    id: int
    titulo: str
    resumo: str
    dt_inicio: datetime.date
    dt_final: datetime.date
    situacao: str
    edital: int
    campus_id: int
    campus_sigla: str
    campus_nome: str
    campus_nome_formatado: str
    nome_coordenador: str
    email_coordenador: str

    @staticmethod
    def resolve_content_type(obj):
        return 'projetos.projeto'

    @staticmethod
    def resolve_id(obj):
        return obj.id

    @staticmethod
    def resolve_titulo(obj):
        return obj.titulo

    @staticmethod
    def resolve_resumo(obj):
        return obj.resumo

    @staticmethod
    def resolve_dt_inicio(obj):
        return obj.inicio_execucao

    @staticmethod
    def resolve_dt_final(obj):
        return obj.fim_execucao

    @staticmethod
    def resolve_situacao(obj):
        return 'Concluído' if obj.is_concluido else 'Em execução'

    @staticmethod
    def resolve_edital(obj):
        return 0

    @staticmethod
    def resolve_campus_id(obj):
        return obj.uo.pk

    @staticmethod
    def resolve_campus_sigla(obj):
        return obj.uo.sigla

    @staticmethod
    def resolve_campus_nome(obj):
        return obj.uo.nome

    @staticmethod
    def resolve_campus_nome_formatado(obj):
        """Remove a palavra 'Campus' do nome do campus, se presente. Retorna o nome em formato Capitalizado."""
        nome = obj.uo.nome
        nome = nome.removeprefix('CAMPUS ')
        return nome.title()  # Retorna o nome em formato Capitalizado

    @staticmethod
    def resolve_nome_coordenador(obj):
        return obj.vinculo_coordenador.pessoa.nome

    @staticmethod
    def resolve_email_coordenador(obj):
        return obj.vinculo_coordenador.user.email
