from ninja import Schema

from contratos.models import Contrato


class ObraSchema(Schema):
    numero_contrato: str
    cnpj_empresa: str | None = None
    razao_social_empresa: str | None = None
    descricao_obra: str
    data_inicio: str
    data_termino: str = None
    valor_obra: float

    @staticmethod
    def resolve_numero_contrato(obj):
        return obj.numero

    @staticmethod
    def resolve_cnpj_empresa(obj: Contrato) -> str | None:
        # A contratada vive em `vinculo_contratado`; `contratada` é legado e vem vazio.
        # Contratada pessoa física não tem CNPJ, e o CPF dela não vai para dado aberto.
        pessoa = obj.vinculo_contratado.pessoa
        return pessoa.pessoajuridica.cnpj if hasattr(pessoa, 'pessoajuridica') else None

    @staticmethod
    def resolve_razao_social_empresa(obj: Contrato) -> str:
        return obj.vinculo_contratado.pessoa.nome

    @staticmethod
    def resolve_descricao_obra(obj):
        return obj.objeto

    @staticmethod
    def resolve_data_inicio(obj):
        return obj.data_inicio.strftime('%d/%m/%Y')

    @staticmethod
    def resolve_data_termino(obj):
        return obj.data_fim.strftime('%d/%m/%Y') if obj.data_fim else ''

    @staticmethod
    def resolve_valor_obra(obj):
        return obj.valor_total
