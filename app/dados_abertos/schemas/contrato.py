from ninja import Schema

from contratos.models import Contrato


class ContratoSchema(Schema):
    numero: str
    ano: int
    campus: str
    objeto: str
    data_inicio: str
    data_termino: str = None
    valor_total: float
    valor_executado: float
    cnpj_contrata: str | None = None
    razao_social_contrata: str | None = None

    @staticmethod
    def resolve_numero(obj):
        return obj.numero

    @staticmethod
    def resolve_ano(obj):
        return obj.data_inicio.year

    @staticmethod
    def resolve_campus(obj):
        return ', '.join(obj.campi.values_list('sigla', flat=True))

    @staticmethod
    def resolve_objeto(obj):
        return obj.objeto

    @staticmethod
    def resolve_data_inicio(obj):
        return obj.data_inicio.strftime('%d/%m/%Y')

    @staticmethod
    def resolve_data_termino(obj):
        return obj.data_fim.strftime('%d/%m/%Y') if obj.data_fim else ''

    @staticmethod
    def resolve_valor_total(obj):
        return obj.valor_total

    @staticmethod
    def resolve_valor_executado(obj):
        return obj.valor_executado

    @staticmethod
    def resolve_cnpj_contrata(obj: Contrato) -> str | None:
        # A contratada vive em `vinculo_contratado`; `contratada` é legado e vem vazio.
        # Contratada pessoa física não tem CNPJ, e o CPF dela não vai para dado aberto.
        pessoa = obj.vinculo_contratado.pessoa
        return pessoa.pessoajuridica.cnpj if hasattr(pessoa, 'pessoajuridica') else None

    @staticmethod
    def resolve_razao_social_contrata(obj: Contrato) -> str:
        return obj.vinculo_contratado.pessoa.nome
